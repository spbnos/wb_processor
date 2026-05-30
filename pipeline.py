"""
Pipeline — склеивает все компоненты в единый поток обработки.

Поток для каждого файла:
  1. FileClassifier.classify()
  2. Если known  → MappingStorage.find_by_struct_hash()
     Если unknown → InteractiveMapper.run() → MappingStorage.save()
  3. ParserEngine.parse()
  4. ErrorHandler.handle_parse_result()
  5. Normalizer.normalize()
  6. ErrorHandler.handle_normalize_result()
  7. DataLoader.load()
  8. ErrorHandler.handle_load_result()
  9. move_to_processed() или move_to_failed()
 10. File record → DB
"""
import logging
import sys
from pathlib import Path

from config.settings import INCOMING_DIR
from classification.file_classifier import FileClassifier
from mapping.mapping_storage import MappingStorage
from mapping.mapping_repository import MappingRepository
from mapping.interactive_mapper import InteractiveMapper
from parsers.parser_engine import ParserEngine
from normalizers.normalizer import Normalizer
from storage.data_loader import DataLoader
from storage.error_handler import ErrorHandler
from watcher.file_watcher import FolderWatcher

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, use_db: bool = False):
        self.use_db = use_db
        self.incoming_dir = INCOMING_DIR

        # Компоненты
        self.storage    = MappingStorage(use_db=use_db)
        self.repo       = MappingRepository(self.storage)
        self.classifier = FileClassifier(self.storage)
        self.mapper     = InteractiveMapper()
        self.parser     = ParserEngine()
        self.normalizer = Normalizer()
        self.loader     = DataLoader(use_db=use_db)
        self.error_handler = ErrorHandler(interactive=True)

        self._watcher = FolderWatcher(
            on_new_file_callback=self.process_file,
            watch_dir=INCOMING_DIR,
        )

    # ─────────────────────────────────────────────────────
    # Главный метод — один файл
    # ─────────────────────────────────────────────────────
    def process_file(self, filepath: Path):
        logger.info(f"[pipeline] ── START: {filepath.name}")
        self.error_handler.clear()
        file_id = self._register_file(filepath)

        try:
            # 1. Классификация
            classification = self.classifier.classify(filepath)

            # 2. Получаем маппинг
            if classification.is_known:
                mapping = self.storage.get_by_id(classification.mapping_id)
                logger.info(f"[pipeline] Known format: '{classification.mapping_name}'")
            else:
                logger.info("[pipeline] Unknown format — starting interactive mapping")
                try:
                    config = self.mapper.run(classification)
                    mapping_obj = self.storage.save(config)
                    mapping = mapping_obj
                    logger.info(f"[pipeline] New mapping saved: '{config.name}'")
                except InterruptedError:
                    logger.info("[pipeline] User cancelled mapping. Skipping file.")
                    self._update_file_status(file_id, "skipped")
                    return

            if not mapping:
                logger.error(f"[pipeline] No mapping found for {filepath.name}")
                self._update_file_status(file_id, "error", "Mapping not found")
                return

            # 3. Parse
            parse_result = self.parser.parse(filepath, mapping)

            # 4. Validate parse
            if not self.error_handler.handle_parse_result(parse_result):
                self._update_file_status(file_id, "error", "Parse validation failed")
                self.error_handler.persist_errors()
                # Если пропала обязательная колонка — предлагаем переконфигурировать
                if parse_result.missing_required:
                    self._offer_remap(filepath, mapping, parse_result)
                return

            # 5. Normalize
            norm_result = self.normalizer.normalize(parse_result, mapping)

            # 6. Validate normalize
            if not self.error_handler.handle_normalize_result(norm_result):
                self._update_file_status(file_id, "error", "Normalize failed")
                self.error_handler.persist_errors()
                return

            # 7. Load
            load_result = self.loader.load(norm_result, mapping, file_id=file_id)

            # 8. Validate load
            if not self.error_handler.handle_load_result(load_result):
                self._update_file_status(file_id, "error", "; ".join(load_result.errors))
                self.error_handler.persist_errors()
                return

            # 9. Успех
            self.error_handler.move_to_processed(filepath)
            self._update_file_status(file_id, "ok", row_count=load_result.rows_total)
            self.error_handler.persist_errors()

            logger.info(
                f"[pipeline] ✅ DONE: {filepath.name} "
                f"| +{load_result.rows_inserted} ins "
                f"| ~{load_result.rows_updated} upd "
                f"| tables: {load_result.tables_written}"
            )

        except Exception as e:
            logger.error(f"[pipeline] Unhandled error for {filepath.name}: {e}", exc_info=True)
            self._update_file_status(file_id, "error", str(e))
            self.error_handler.persist_errors()

    # ─────────────────────────────────────────────────────
    def scan_existing(self):
        """Обработать файлы уже лежащие в incoming/."""
        self._watcher.scan_existing()

    def run_forever(self):
        """Блокирующий режим — Ctrl+C для остановки."""
        self._watcher.run_forever()

    def start(self):
        self._watcher.start()

    def stop(self):
        self._watcher.stop()

    # ─────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────
    def _register_file(self, filepath: Path) -> int:
        """Регистрирует файл в таблице files. Возвращает id."""
        if not self.use_db:
            return 0  # JSON-режим не требует file_id
        try:
            from db.database import SessionLocal
            from db.models import File
            from classification.file_classifier import compute_file_hash
            from datetime import datetime

            with SessionLocal() as db:
                f = File(
                    filename=filepath.name,
                    filepath=str(filepath),
                    file_hash=compute_file_hash(filepath),
                    extension=filepath.suffix.lower(),
                    size_bytes=filepath.stat().st_size,
                    status="pending",
                    created_at=datetime.utcnow(),
                )
                db.add(f)
                db.commit()
                db.refresh(f)
                return f.id
        except Exception as e:
            logger.warning(f"[pipeline] Cannot register file: {e}")
            return 0

    def _update_file_status(self, file_id: int, status: str, error: str = "", row_count: int = 0):
        if not self.use_db or not file_id:
            return
        try:
            from db.database import SessionLocal
            from db.models import File
            from datetime import datetime
            with SessionLocal() as db:
                f = db.query(File).filter_by(id=file_id).first()
                if f:
                    f.status = status
                    f.error_msg = error or None
                    f.row_count = row_count or f.row_count
                    f.processed_at = datetime.utcnow()
                    db.commit()
        except Exception as e:
            logger.warning(f"[pipeline] Cannot update file status: {e}")

    def _offer_remap(self, filepath: Path, mapping, parse_result):
        """Предлагает переконфигурировать маппинг если пропала обязательная колонка."""
        from rich.console import Console
        from rich.prompt import Confirm
        c = Console()
        c.print(
            f"\n[yellow]⚠  Обязательные колонки пропали:[/] "
            f"{parse_result.missing_required}\n"
        )
        if Confirm.ask("  Переконфигурировать маппинг прямо сейчас?", default=True):
            from classification.file_classifier import ClassificationResult
            # Создаём фейковый результат классификации для ремаппинга
            classification = self.classifier.classify(filepath)
            classification_for_remap = ClassificationResult(
                signature=classification.signature,
                mapping_id=mapping.id,
                mapping_name=mapping.name,
                is_known=False,   # форсируем интерактивный маппер
            )
            try:
                config = self.mapper.run(classification_for_remap)
                config.name = mapping.name   # сохраняем имя
                config.struct_hash = mapping.struct_hash  # тот же хэш
                # Удаляем старый и сохраняем новый
                self.storage.delete(mapping.id, hard=True)
                self.storage.save(config)
                c.print("[bold green]✅ Маппинг обновлён. Повторно запусти scan.[/]")
            except InterruptedError:
                c.print("[dim]Отменено.[/]")
