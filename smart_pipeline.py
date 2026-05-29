"""
smart_pipeline.py — unified pipeline с CanonicalReportClassifier + Domain Parsers.

Поток обработки:
  1. CanonicalReportClassifier → определяет тип отчёта (8 типов WB)
     confidence ≥ 0.7 → DomainParserFactory → DomainLoader → data/loaded/{table}.json
     confidence < 0.7 → SmartMapper fallback → transactions

  2. SmartMapper fallback:
     AUTO_APPLY  → сохранить MappingConfig → ParserEngine → DataLoader
     NEEDS_REVIEW → enqueue → продолжить с частичным маппингом
     LOW_CONF blocking → deferred/
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

from config.settings import INCOMING_DIR, PROCESSED_DIR, DEFERRED_DIR, FAILED_DIR
from mapping.mapping_storage import MappingStorage
from mapping.mapping_repository import MappingRepository
from classification.file_classifier import FileClassifier, compute_file_hash
from parsers.parser_engine import ParserEngine, _read_raw
from normalizers.normalizer import Normalizer
from storage.data_loader import DataLoader
from storage.error_handler import ErrorHandler
from review_queue.queue_store import ReviewQueue
from review_queue.mapping_bridge import (
    build_review_items,
    smart_result_to_config,
    apply_review_decisions,
)
from smart_mapping.smart_mapper import SmartMapper
from smart_mapping.confidence_scorer import ConfidenceLevel
from core.processed_registry import ProcessedFileRegistry
from watcher.file_watcher import FolderWatcher

# ── Canonical классификатор (новый, Фаза 2) ──────────────────────────────────
try:
    from classification.canonical_report_registry import CanonicalReportClassifier
    from parsers.domain.domain_parser_factory import DomainParserFactory
    from storage.domain_loader import DomainLoader
    _CANONICAL_AVAILABLE = True
except ImportError as _e:
    _CANONICAL_AVAILABLE = False
    logging.getLogger(__name__).warning(
        f"[smart_pipeline] CanonicalReportClassifier not available: {_e}. "
        "Running in SmartMapper-only mode."
    )

logger = logging.getLogger(__name__)
_DEFAULT_CATEGORY = "external"


class SmartPipeline:
    """
    Production pipeline с AI-маппингом и Domain Parsers.

    Использование:
        pipeline = SmartPipeline(use_db=False)
        pipeline.scan_existing()   # обработать incoming/
        pipeline.run_forever()     # watchdog режим
    """

    def __init__(
        self,
        use_db: bool = False,
        auto_threshold: float = 0.75,
        review_threshold: float = 0.40,
    ):
        self.use_db = use_db
        self.incoming_dir = INCOMING_DIR

        # Базовые компоненты
        self.storage       = MappingStorage(use_db=use_db)
        self.repo          = MappingRepository(self.storage)
        self.classifier    = FileClassifier(self.storage)
        self.parser        = ParserEngine()
        self.normalizer    = Normalizer()
        self.loader        = DataLoader(use_db=use_db)
        self.error_handler = ErrorHandler(interactive=False)
        self.smart_mapper  = SmartMapper(
            use_db=use_db,
            auto_threshold=auto_threshold,
            review_threshold=review_threshold,
        )
        self.review_queue  = ReviewQueue(use_db=use_db)
        self._registry     = ProcessedFileRegistry()

        # Canonical компоненты (Фаза 2)
        if _CANONICAL_AVAILABLE:
            self.canon_classifier = CanonicalReportClassifier()
            self.domain_loader    = DomainLoader(use_db=use_db)
            logger.info("[smart_pipeline] CanonicalReportClassifier enabled (8 report types)")
        else:
            self.canon_classifier = None
            self.domain_loader    = None

        self._watcher = FolderWatcher(
            on_new_file_callback=self.process_file,
            watch_dir=INCOMING_DIR,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Главный метод
    # ─────────────────────────────────────────────────────────────────────────

    def process_file(self, filepath: Path) -> str:
        """
        Обрабатывает один файл.
        Возвращает статус: "ok" | "queued" | "deferred" | "skipped" | "error"
        """
        logger.info(f"[smart_pipeline] ── START: {filepath.name}")
        self.error_handler.clear()

        # Дедупликация
        file_hash = compute_file_hash(filepath)
        if self._registry.is_processed(file_hash):
            prev = self._registry.get(file_hash) or {}
            logger.info(f"[smart_pipeline] SKIP (already processed): {filepath.name}")
            self.error_handler.move_to_processed(filepath)
            return "skipped"

        file_id = self._register_file(filepath)

        try:
            # ── ПУТЬ 1: CanonicalReportClassifier ────────────────────────────
            if self.canon_classifier is not None:
                canon = self.canon_classifier.classify(filepath)
                logger.info(
                    f"[smart_pipeline] Canonical: {filepath.name} → "
                    f"{canon.report_type.report_id if canon.report_type else 'unknown'} "
                    f"(conf={canon.confidence:.2f}, reason={canon.match_reason})"
                )

                if canon.report_type is not None and canon.confidence >= 0.7:
                    result = DomainParserFactory.parse(filepath, canon)

                    if result is None or not result.ok:
                        errs = result.errors if result else ["factory returned None"]
                        logger.error(f"[smart_pipeline] Domain parse failed: {errs}")
                        self._registry.register(file_hash, filepath.name, status="error", error=str(errs))
                        import shutil; shutil.move(str(filepath), str(FAILED_DIR / filepath.name))
                        return "error"

                    load = self.domain_loader.load(result, file_id=file_id)
                    if not load.ok:
                        logger.error(f"[smart_pipeline] Domain load failed: {load.errors}")
                        self._registry.register(file_hash, filepath.name, status="error", error=str(load.errors))
                        import shutil; shutil.move(str(filepath), str(FAILED_DIR / filepath.name))
                        return "error"

                    self._registry.register(
                        file_hash, filepath.name, status="ok",
                        row_count=load.rows_written,
                        extra={
                            "report_type": canon.report_type.report_id,
                            "domain":      canon.report_type.domain,
                            "db_table":    load.db_table,
                            "period_from": result.period_from,
                            "period_to":   result.period_to,
                        }
                    )
                    import shutil; shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
                    logger.info(
                        f"[smart_pipeline] ✅ CANONICAL {filepath.name} → "
                        f"{load.db_table} +{load.rows_written} rows"
                    )
                    return "ok"

                # Известный тип но низкий confidence → попробуем SmartMapper
                logger.info(
                    f"[smart_pipeline] Low canonical confidence ({canon.confidence:.2f}) "
                    f"→ SmartMapper fallback for {filepath.name}"
                )

            # ── ПУТЬ 2: SmartMapper fallback ─────────────────────────────────
            return self._smart_mapper_path(filepath, file_hash, file_id)

        except Exception as e:
            logger.error(f"[smart_pipeline] Unhandled: {filepath.name}: {e}", exc_info=True)
            self._update_file_status(file_id, "error", str(e))
            self._registry.register(file_hash, filepath.name, status="error", error=str(e))
            self.error_handler.persist_errors()
            return "error"

    # ─────────────────────────────────────────────────────────────────────────
    # SmartMapper fallback path (Фаза 1)
    # ─────────────────────────────────────────────────────────────────────────

    def _smart_mapper_path(self, filepath: Path, file_hash: str, file_id: int) -> str:
        """Fallback: классический pipeline через SmartMapper."""
        classification = self.classifier.classify(filepath)
        mapping = self._resolve_mapping(filepath, classification)

        if mapping is None:
            logger.warning(f"[smart_pipeline] DEFERRED: {filepath.name} (low confidence)")
            self._move_to_deferred(filepath)
            self._update_file_status(file_id, "deferred")
            self._registry.register(file_hash, filepath.name, status="deferred", error="low_confidence_mapping")
            return "deferred"

        parse_result = self.parser.parse(filepath, mapping)
        if not self.error_handler.handle_parse_result(parse_result):
            self._trigger_remap(filepath, classification, file_id)
            return "error"

        norm_result = self.normalizer.normalize(parse_result, mapping)
        if not self.error_handler.handle_normalize_result(norm_result):
            self._update_file_status(file_id, "error", "normalize_failed")
            self.error_handler.persist_errors()
            return "error"

        load_result = self.loader.load(norm_result, mapping, file_id=file_id, file_hash=file_hash)
        if not self.error_handler.handle_load_result(load_result):
            self._update_file_status(file_id, "error", "; ".join(load_result.errors))
            self._registry.register(file_hash, filepath.name, status="error", error="; ".join(load_result.errors))
            self.error_handler.persist_errors()
            return "error"

        self.error_handler.move_to_processed(filepath)
        self._update_file_status(file_id, "ok", row_count=load_result.rows_total)
        self._registry.register(file_hash, filepath.name, status="ok", row_count=load_result.rows_total)
        self.error_handler.persist_errors()

        pending = self.review_queue.count_pending()
        status  = "queued" if pending > 0 else "ok"
        logger.info(
            f"[smart_pipeline] ✅ SMARTMAPPER {filepath.name} "
            f"status={status} +{load_result.rows_inserted}ins pending_reviews={pending}"
        )
        return status

    # ─────────────────────────────────────────────────────────────────────────
    # Маппинг (SmartMapper path)
    # ─────────────────────────────────────────────────────────────────────────

    def _resolve_mapping(self, filepath: Path, classification):
        if classification.is_known:
            mapping = self.storage.get_by_id(classification.mapping_id)
            if mapping:
                logger.info(f"[smart_pipeline] Known mapping: '{mapping.name}'")
                return mapping

        logger.info(f"[smart_pipeline] Unknown format — running SmartMapper")
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
            f"auto={smart_result.auto_count} review={smart_result.review_count} "
            f"ignored={smart_result.ignored_count} avg_conf={smart_result.avg_confidence:.3f} "
            f"can_proceed={smart_result.can_proceed}"
        )

        if not smart_result.can_proceed and smart_result.auto_count == 0:
            logger.warning("[smart_pipeline] No recognized columns — file deferred")
            if smart_result.review_count > 0:
                self._enqueue_review(smart_result, filepath, sample_df)
            return None

        config = smart_result_to_config(
            result=smart_result,
            name=f"auto:{filepath.stem}",
            category=self._infer_category(filepath, sample_df),
        )
        saved = self.storage.save(config)
        logger.info(f"[smart_pipeline] Saved new mapping: '{config.name}' id={saved.id}")

        if smart_result.review_count > 0:
            self._enqueue_review(smart_result, filepath, sample_df)

        return saved

    def _enqueue_review(self, smart_result, filepath: Path, sample_df: pd.DataFrame):
        sample_values = {col: sample_df[col].dropna().tolist()[:5] for col in sample_df.columns}
        items = build_review_items(smart_result, filepath, sample_values)
        if items:
            self.review_queue.enqueue_many(items)
            logger.info(f"[smart_pipeline] Enqueued {len(items)} items for review")

    def _trigger_remap(self, filepath: Path, classification, file_id: int):
        logger.warning("[smart_pipeline] Required column missing — forcing remap")
        if classification.is_known and classification.mapping_id:
            self.storage.delete(classification.mapping_id, hard=True)
        self._update_file_status(file_id, "error", "required_column_missing_remap_triggered")
        self.error_handler.persist_errors()

    @staticmethod
    def _infer_category(filepath: Path, sample_df: pd.DataFrame) -> str:
        name = filepath.name.lower()
        if any(kw in name for kw in ["продаж","реализ","детализир","ежедневн","отчет","report","wb_"]):
            return "wb_report"
        if any(kw in name for kw in ["advert","рекл","campaign","кампан","затрат"]):
            return "ad"
        if sample_df is not None:
            cols = " ".join(c.lower() for c in sample_df.columns)
            if any(kw in cols for kw in ["вайлдберриз реализовал","к перечислению продавцу","вознаграждение вайлдберриз"]):
                return "wb_report"
        return "external"

    def apply_pending_reviews(self, struct_hash: str) -> int:
        count = apply_review_decisions(struct_hash, self.review_queue, self.storage)
        if count:
            logger.info(f"[smart_pipeline] Applied {count} review decisions for {struct_hash}")
        return count

    # ── Public API ────────────────────────────────────────────────────────────

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
            "review_queue":      self.review_queue.stats(),
            "learning_store":    self.smart_mapper._store.stats(),
            "processed_registry":self._registry.stats(),
        }

    @staticmethod
    def _move_to_deferred(filepath: Path):
        import shutil
        dest = DEFERRED_DIR / filepath.name
        if dest.exists():
            dest = DEFERRED_DIR / f"{filepath.stem}_{int(time.time())}{filepath.suffix}"
        shutil.move(str(filepath), str(dest))
        logger.info(f"[smart_pipeline] Moved to deferred/: {dest.name}")

    def _register_file(self, filepath: Path) -> int:
        if not self.use_db:
            return 0
        try:
            from db.database import SessionLocal
            from db.models import File
            from datetime import datetime, timezone
            with SessionLocal() as db:
                f = File(
                    filename=filepath.name, filepath=str(filepath),
                    file_hash=compute_file_hash(filepath),
                    extension=filepath.suffix.lower(),
                    size_bytes=filepath.stat().st_size,
                    status="pending", created_at=datetime.now(timezone.utc),
                )
                db.add(f); db.commit(); db.refresh(f)
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
                    f.status = status; f.error_msg = error or None
                    f.row_count = row_count or f.row_count
                    f.processed_at = datetime.now(timezone.utc)
                    db.commit()
        except Exception as e:
            logger.warning(f"[smart_pipeline] Cannot update file status: {e}")
