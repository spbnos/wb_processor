"""
smart_pipeline.py — обновлённый Pipeline с SmartMapper вместо InteractiveMapper.

Новый поток:
  1.  FileClassifier.classify()
  2a. Known format  → MappingStorage.find_by_struct_hash()
  2b. Unknown format → SmartMapper.map_file()
        → AUTO_APPLY  → сохранить MappingConfig → продолжить
        → NEEDS_REVIEW → enqueue в ReviewQueue → продолжить с частичным маппингом
        → can_proceed=False → отложить файл (LOW_CONF blocking)
  3.  ParserEngine.parse()
  4.  ErrorHandler.handle_parse_result()
  5.  Normalizer.normalize()
  6.  ErrorHandler.handle_normalize_result()
  7.  DataLoader.load()
  8.  ErrorHandler.handle_load_result()
  9.  move_to_processed()

Zero manual input. Только если confidence < threshold — item попадает в ReviewQueue
и Dashboard покажет его пользователю.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.paths import ensure_wb_platform_on_path

ensure_wb_platform_on_path()

import pandas as pd

from config.settings import INCOMING_DIR
from classification.file_classifier import FileClassifier
from mapping.mapping_storage import MappingStorage
from mapping.mapping_repository import MappingRepository
from parsers.parser_engine import ParserEngine, _read_raw
from normalizers.normalizer import Normalizer
from storage.data_loader import DataLoader
from storage.error_handler import ErrorHandler
from watcher.file_watcher import FolderWatcher
from review_queue.queue_store import ReviewQueue
from review_queue.mapping_bridge import (
    smart_result_to_config,
    build_review_items,
    apply_review_decisions,
)

from smart_mapping.smart_mapper import SmartMapper
from smart_mapping.confidence_scorer import ConfidenceLevel
from core.processed_registry import ProcessedFileRegistry
from classification.file_classifier import compute_file_hash

logger = logging.getLogger(__name__)

# ─── Категория по умолчанию — переопределяется через classifier ─────
_DEFAULT_CATEGORY = "external"


class SmartPipeline:
    """
    Production pipeline с AI-маппингом.

    Использование:
        pipeline = SmartPipeline(use_db=False)
        pipeline.scan_existing()   # обработать incoming/
        pipeline.run_forever()     # watchdog режим
    """

    def __init__(
        self,
        use_db: bool = False,
        auto_threshold: float = 0.75,   # снижено для WB файлов
        review_threshold: float = 0.40,  # снижено — WB колонки специфичны
    ):
        self.use_db = use_db
        self.incoming_dir = INCOMING_DIR

        # Существующие компоненты (Фаза 0)
        self.storage    = MappingStorage(use_db=use_db)
        self.repo       = MappingRepository(self.storage)
        self.classifier = FileClassifier(self.storage)
        self.parser     = ParserEngine()
        self.normalizer = Normalizer()
        self.loader     = DataLoader(use_db=use_db)
        self.error_handler = ErrorHandler(interactive=False)  # нет CLI вопросов

        # Новые компоненты (Фаза 1)
        self.smart_mapper = SmartMapper(
            use_db=use_db,
            auto_threshold=auto_threshold,
            review_threshold=review_threshold,
        )
        self.review_queue = ReviewQueue(use_db=use_db)
        self._registry = ProcessedFileRegistry()

        self._watcher = FolderWatcher(
            on_new_file_callback=self.process_file,
            watch_dir=INCOMING_DIR,
        )

    # ─────────────────────────────────────────────────────
    # Главный метод
    # ─────────────────────────────────────────────────────

    def process_file(self, filepath: Path) -> str:
        """
        Обрабатывает один файл.
        Возвращает статус: "ok" | "queued" | "deferred" | "error"
        """
        logger.info(f"[smart_pipeline] ── START: {filepath.name}")
        self.error_handler.clear()

        file_hash = compute_file_hash(filepath)
        if self._registry.is_processed(file_hash):
            prev = self._registry.get(file_hash) or {}
            logger.info(
                f"[smart_pipeline] SKIP (already processed): {filepath.name} "
                f"at {prev.get('processed_at', '?')}"
            )
            self.error_handler.move_to_processed(filepath)
            return "skipped"

        file_id = self._register_file(filepath)

        try:
            # ── 1. Классификация ──────────────────────────────────
            classification = self.classifier.classify(filepath)

            # ── 2. Маппинг ────────────────────────────────────────
            mapping = self._resolve_mapping(filepath, classification)

            if mapping is None:
                logger.warning(f"[smart_pipeline] DEFERRED: {filepath.name} (low confidence)")
                self._move_to_deferred(filepath)
                self._update_file_status(file_id, "deferred")
                self._registry.register(
                    file_hash, filepath.name, status="deferred",
                    error="low_confidence_mapping",
                )
                return "deferred"

            # ── 3. Parse ──────────────────────────────────────────
            parse_result = self.parser.parse(filepath, mapping)

            if not self.error_handler.handle_parse_result(parse_result):
                # Обязательная колонка пропала → пробуем ремаппинг
                self._trigger_remap(filepath, classification, file_id)
                return "error"

            # ── 4. Normalize ──────────────────────────────────────
            norm_result = self.normalizer.normalize(parse_result, mapping)

            if not self.error_handler.handle_normalize_result(norm_result):
                self._update_file_status(file_id, "error", "normalize_failed")
                self.error_handler.persist_errors()
                return "error"

            # ── 5. Load ───────────────────────────────────────────
            load_result = self.loader.load(
                norm_result, mapping, file_id=file_id, file_hash=file_hash,
            )

            if not self.error_handler.handle_load_result(load_result):
                self._update_file_status(file_id, "error", "; ".join(load_result.errors))
                self._registry.register(
                    file_hash, filepath.name, status="error",
                    error="; ".join(load_result.errors),
                )
                self.error_handler.persist_errors()
                return "error"

            # ── 6. Успех ──────────────────────────────────────────
            self.error_handler.move_to_processed(filepath)
            self._update_file_status(file_id, "ok", row_count=load_result.rows_total)
            self._registry.register(
                file_hash, filepath.name, status="ok",
                row_count=load_result.rows_total,
            )
            self.error_handler.persist_errors()

            # Статус с учётом review queue
            pending = self.review_queue.count_pending()
            status = "queued" if pending > 0 else "ok"

            logger.info(
                f"[smart_pipeline] ✅ {filepath.name} "
                f"status={status} "
                f"+{load_result.rows_inserted}ins "
                f"pending_reviews={pending}"
            )
            return status

        except Exception as e:
            logger.error(f"[smart_pipeline] Unhandled: {filepath.name}: {e}", exc_info=True)
            self._update_file_status(file_id, "error", str(e))
            self._registry.register(file_hash, filepath.name, status="error", error=str(e))
            self.error_handler.persist_errors()
            return "error"

    # ─────────────────────────────────────────────────────
    # Маппинг
    # ─────────────────────────────────────────────────────

    def _resolve_mapping(self, filepath: Path, classification):
        """
        Возвращает MappingObj или None (если blocking LOW_CONF).

        Логика:
            known format  → из storage
            unknown       → SmartMapper:
                AUTO_APPLY   → сохранить + вернуть
                NEEDS_REVIEW → сохранить + enqueue → вернуть (обработка идёт)
                LOW_CONF blocking → вернуть None (отложить)
        """
        # Known format
        if classification.is_known:
            mapping = self.storage.get_by_id(classification.mapping_id)
            if mapping:
                logger.info(f"[smart_pipeline] Known: '{mapping.name}'")
                return mapping

        # Unknown → SmartMapper
        logger.info(f"[smart_pipeline] Unknown format — running SmartMapper")

        # Читаем sample для SmartMapper
        try:
            sample_df = _read_raw(filepath).head(30)
        except Exception as e:
            logger.error(f"[smart_pipeline] Cannot read sample: {e}")
            return None

        smart_result = self.smart_mapper.map_file(
            filepath=filepath,
            struct_hash=classification.signature.struct_hash,
            sample_df=sample_df,
        )

        logger.info(
            f"[smart_pipeline] SmartMapper: "
            f"auto={smart_result.auto_count} "
            f"review={smart_result.review_count} "
            f"ignored={smart_result.ignored_count} "
            f"avg_conf={smart_result.avg_confidence:.3f} "
            f"can_proceed={smart_result.can_proceed}"
        )

        # Blocking LOW_CONF — если много неизвестных колонок, всё равно продолжаем
        # Unknown WB-specific columns просто игнорируем
        if not smart_result.can_proceed and smart_result.auto_count == 0:
            logger.warning(
                f"[smart_pipeline] No recognized columns at all — file deferred"
            )
            self._enqueue_review(smart_result, filepath, sample_df)
            return None
        elif not smart_result.can_proceed:
            logger.warning(
                f"[smart_pipeline] Blocking fields: {smart_result.blocking_fields} — proceeding anyway with partial mapping"
            )
            self._enqueue_review(smart_result, filepath, sample_df)

        # Сохраняем маппинг
        config = smart_result_to_config(
            result=smart_result,
            name=f"auto:{filepath.stem}",
            category=self._infer_category(filepath, sample_df),
        )
        saved = self.storage.save(config)
        logger.info(f"[smart_pipeline] Saved new mapping: '{config.name}' id={saved.id}")

        # Enqueue NEEDS_REVIEW items (не блокируют, но показываются в Dashboard)
        if smart_result.review_count > 0:
            self._enqueue_review(smart_result, filepath, sample_df)

        return saved

    def _enqueue_review(
        self,
        smart_result,
        filepath: Path,
        sample_df: pd.DataFrame,
    ):
        """Добавляет NEEDS_REVIEW/LOW_CONF решения в ReviewQueue."""
        sample_values = {
            col: sample_df[col].dropna().tolist()[:5]
            for col in sample_df.columns
        }
        items = build_review_items(smart_result, filepath, sample_values)
        if items:
            self.review_queue.enqueue_many(items)
            logger.info(f"[smart_pipeline] Enqueued {len(items)} items for review")

    def _trigger_remap(self, filepath: Path, classification, file_id: int):
        """Обязательная колонка пропала — форсируем полный ремаппинг."""
        logger.warning(f"[smart_pipeline] Required column missing — forcing remap")
        # Удаляем старый маппинг чтобы SmartMapper пересчитал
        if classification.is_known and classification.mapping_id:
            self.storage.delete(classification.mapping_id, hard=True)
        self._update_file_status(file_id, "error", "required_column_missing_remap_triggered")
        self.error_handler.persist_errors()

    @staticmethod
    def _infer_category(filepath: Path, sample_df: pd.DataFrame) -> str:
        name = filepath.name.lower()
        wb_name_keys = ["sales","продаж","realization","реализ","детализир","ежедневн","отчет","report","wb_"]
        if any(kw in name for kw in wb_name_keys):
            return "wb_report"
        if any(kw in name for kw in ["advert","рекл","campaign","кампан"]):
            return "ad"
        if sample_df is not None:
            cols = " ".join(c.lower() for c in sample_df.columns)
            if any(kw in cols for kw in ["вайлдберриз реализовал","к перечислению продавцу","вознаграждение вайлдберриз"]):
                return "wb_report"
        return "external"

    # ── Apply review decisions ────────────────────────────

    def apply_pending_reviews(self, struct_hash: str) -> int:
        """
        Применяет подтверждённые пользователем review decisions.
        Вызывается из API после того как пользователь нажал "Approve" в Dashboard.
        """
        count = apply_review_decisions(struct_hash, self.review_queue, self.storage)
        if count:
            logger.info(f"[smart_pipeline] Applied {count} review decisions for {struct_hash}")
        return count

    # ── Public API ────────────────────────────────────────

    def scan_existing(self):
        self._watcher.scan_existing()

    def run_forever(self):
        self._watcher.run_forever()

    def start(self):
        self._watcher.start()

    def stop(self):
        self._watcher.stop()

    def queue_stats(self) -> dict:
        return {
            "review_queue": self.review_queue.stats(),
            "learning_store": self.smart_mapper._store.stats(),
            "processed_registry": self._registry.stats(),
        }

    @staticmethod
    def _move_to_deferred(filepath: Path):
        from config.settings import DEFERRED_DIR
        import shutil
        dest = DEFERRED_DIR / filepath.name
        if dest.exists():
            dest = DEFERRED_DIR / f"{filepath.stem}_{int(time.time())}{filepath.suffix}"
        shutil.move(str(filepath), str(dest))
        logger.info(f"[smart_pipeline] Moved to deferred/: {dest.name}")

    # ── DB helpers ────────────────────────────────────────

    def _register_file(self, filepath: Path) -> int:
        if not self.use_db:
            return 0
        try:
            from db.database import SessionLocal
            from db.models import File
            from classification.file_classifier import compute_file_hash
            from datetime import datetime, timezone
            with SessionLocal() as db:
                f = File(
                    filename=filepath.name,
                    filepath=str(filepath),
                    file_hash=compute_file_hash(filepath),
                    extension=filepath.suffix.lower(),
                    size_bytes=filepath.stat().st_size,
                    status="pending",
                    created_at=datetime.now(timezone.utc),
                )
                db.add(f)
                db.commit()
                db.refresh(f)
                return f.id
        except Exception as e:
            logger.warning(f"[smart_pipeline] Cannot register file: {e}")
            return 0

    def _update_file_status(self, file_id: int, status: str, error: str = "", row_count: int = 0):
        if not self.use_db or not file_id:
            return
        try:
            from db.database import SessionLocal
            from db.models import File
            from datetime import datetime, timezone
            with SessionLocal() as db:
                f = db.query(File).filter_by(id=file_id).first()
                if f:
                    f.status = status
                    f.error_msg = error or None
                    f.row_count = row_count or f.row_count
                    f.processed_at = datetime.now(timezone.utc)
                    db.commit()
        except Exception as e:
            logger.warning(f"[smart_pipeline] Cannot update file status: {e}")
