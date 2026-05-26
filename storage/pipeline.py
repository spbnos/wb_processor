"""
Pipeline — склеивает все шаги в единый поток обработки файла.

Поток:
    filepath
      → FileClassifier     (known / unknown)
      → InteractiveMapper  (если unknown)
      → MappingStorage     (save / load)
      → ParserEngine       (parse)
      → ErrorHandler       (check parse result)
      → Normalizer         (clean types)
      → ErrorHandler       (check type warnings)
      → DataLoader         (upsert to DB / CSV)
      → ErrorHandler       (check load result)
      → move to processed/
"""
import logging
import shutil
from datetime import datetime
from pathlib import Path

from config.settings import PROCESSED_DIR
from classification.file_classifier import FileClassifier
from mapping.mapping_storage import MappingStorage
from mapping.interactive_mapper import InteractiveMapper
from parsers.parser_engine import ParserEngine
from normalizers.normalizer import Normalizer
from storage.data_loader import DataLoader
from storage.error_handler import ErrorHandler
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


class Pipeline:
    """
    Главный оркестратор.

    Использование:
        pipeline = Pipeline(use_db=False)
        pipeline.process(Path("incoming/wb_sales.xlsx"))
    """

    def __init__(self, use_db: bool = True):
        self._storage = MappingStorage(use_db=use_db)
        self._classifier = FileClassifier(self._storage)
        self._mapper = InteractiveMapper()
        self._parser = ParserEngine()
        self._normalizer = Normalizer()
        self._loader = DataLoader(use_db=use_db)
        self._error_handler = ErrorHandler(on_remap_needed=self._handle_remap)

    def process(self, filepath: Path) -> bool:
        """
        Обрабатывает один файл.
        Возвращает True если успешно, False если ошибка.
        """
        console.print(f"\n[bold cyan]▶ Обработка:[/] {filepath.name}")
        start = datetime.utcnow()

        # ── 1. Классификация ──────────────────────────────
        try:
            clf_result = self._classifier.classify(filepath)
        except Exception as e:
            logger.error(f"[pipeline] Classify failed: {e}")
            console.print(f"[red]Ошибка классификации: {e}[/]")
            return False

        # ── 2. Маппинг (новый или известный) ─────────────
        if clf_result.is_known:
            mapping = self._storage.find_by_struct_hash(clf_result.signature.struct_hash)
            console.print(f"[green]✓ Известный формат:[/] {mapping.name}")
        else:
            console.print("[yellow]Новый формат — требуется настройка[/]")
            try:
                config = self._mapper.run(clf_result)
                mapping = self._storage.save(config)
            except InterruptedError:
                console.print("[yellow]Настройка отменена. Файл пропущен.[/]")
                return False
            except Exception as e:
                logger.error(f"[pipeline] Mapping failed: {e}")
                return False

        if mapping is None:
            console.print("[red]Маппинг не найден/не создан[/]")
            return False

        # ── 3. Парсинг ────────────────────────────────────
        parse_result = self._parser.parse(filepath, mapping)
        if not self._error_handler.handle_parse_error(parse_result, mapping):
            return False

        # ── 4. Нормализация ───────────────────────────────
        norm_result = self._normalizer.normalize(parse_result, mapping)
        self._error_handler.handle_normalize_warning(norm_result, mapping)

        if not norm_result.ok:
            console.print("[red]Нормализация не удалась[/]")
            return False

        # ── 5. Загрузка в БД ──────────────────────────────
        file_id = self._loader.register_file(
            filepath=filepath,
            mapping_id=mapping.id,
            file_hash=clf_result.signature.file_hash,
            struct_hash=clf_result.signature.struct_hash,
            row_count=norm_result.row_count,
            status="processing",
        )

        load_result = self._loader.load(norm_result, mapping, file_id=file_id)
        self._error_handler.handle_load_error(load_result)

        # Обновляем статус файла
        self._loader.register_file(
            filepath=filepath,
            mapping_id=mapping.id,
            file_hash=clf_result.signature.file_hash,
            struct_hash=clf_result.signature.struct_hash,
            row_count=norm_result.row_count,
            status="ok" if load_result.ok else "error",
        )

        # ── 6. Перемещаем в processed/ ───────────────────
        if load_result.ok:
            self._move_to_processed(filepath)
            elapsed = (datetime.utcnow() - start).total_seconds()
            console.print(
                f"[bold green]✅ Готово:[/] {norm_result.row_count} строк → "
                f"'{load_result.table}' за {elapsed:.1f}с"
            )
            return True
        else:
            console.print(
                f"[red]Загружено с ошибками: "
                f"+{load_result.rows_inserted} / ~{load_result.rows_updated} / "
                f"-{load_result.rows_skipped} skipped[/]"
            )
            return False

    def _handle_remap(self, filepath: Path, old_mapping):
        """Callback для re-mapping при пропавших колонках."""
        from classification.file_classifier import FileClassifier
        clf = FileClassifier(self._storage)
        clf_result = clf.classify(filepath)
        config = self._mapper.run(clf_result)
        self._storage.update(old_mapping.id, **{
            "name": config.name,
            "fields": config.fields,
            "notes": config.notes,
        })

    def _move_to_processed(self, filepath: Path):
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        dest = PROCESSED_DIR / f"{ts}_{filepath.name}"
        try:
            shutil.move(str(filepath), dest)
            logger.info(f"[pipeline] Moved to processed: {dest.name}")
        except Exception as e:
            logger.warning(f"[pipeline] Could not move file: {e}")
