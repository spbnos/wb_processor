"""
Подключение knowledge_base к SmartMapper (wb_processor root в sys.path).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from knowledge_base.search.knowledge_engine import KnowledgeEngine, FieldLookupResult

logger = logging.getLogger(__name__)

# wb_platform/smart_mapping → wb_processor
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_engine: Optional["KnowledgeEngine"] = None
_kb_ready = False


def _ensure_project_path() -> None:
    root = str(_PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def get_knowledge_engine() -> "KnowledgeEngine":
    """Singleton KnowledgeEngine + PDF-термины из оферты."""
    global _engine, _kb_ready
    _ensure_project_path()

    if _engine is None:
        from knowledge_base.search.knowledge_engine import KnowledgeEngine

        _engine = KnowledgeEngine()
        _bootstrap_pdf_terms(_engine)
        _kb_ready = True
        stats = _engine.stats()
        logger.info(
            f"[kb_integration] Ready: {stats['total_fields']} registry fields, "
            f"{stats['pdf_terms']} PDF terms"
        )

    return _engine


def _bootstrap_pdf_terms(engine: "KnowledgeEngine") -> None:
    """Загружает pdf_index.json и при необходимости парсит PDF из documents/."""
    from knowledge_base.pdf_reader import PDFReader

    reader = PDFReader()
    loaded = reader.load_saved_index()
    if loaded:
        reader.enrich_knowledge_engine(engine)
        return

    pdfs = sorted(reader._docs_dir.glob("*.pdf"))
    if not pdfs:
        logger.warning("[kb_integration] No PDF in knowledge_base/documents/")
        return

    reader.load_all()
    enriched = reader.enrich_knowledge_engine(engine)
    reader.save_index()
    logger.info(f"[kb_integration] Indexed {enriched} terms from {len(pdfs)} PDF(s)")


def kb_lookup(column: str) -> Optional["FieldLookupResult"]:
    return get_knowledge_engine().lookup(column)
