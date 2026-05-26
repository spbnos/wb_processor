"""
api/routes/kb.py — Knowledge Base API

GET  /api/kb/status          — статус KB (документы, термины)
GET  /api/kb/documents        — список PDF документов
POST /api/kb/index            — переиндексировать все PDF
GET  /api/kb/search?q=...     — поиск по текстам документов
GET  /api/kb/field?col=...    — найти поле по названию колонки
GET  /api/kb/terms?q=...      — поиск по извлечённым терминам
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.auth import require_auth

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

# Lazy-init
_reader = None
_engine = None


def _get_reader():
    global _reader
    if _reader is None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from knowledge_base.pdf_reader import PDFReader
        _reader = PDFReader()
        _reader.load_saved_index()   # загружаем сохранённый индекс (быстро)
    return _reader


def _get_engine():
    global _engine
    if _engine is None:
        from knowledge_base.search.knowledge_engine import KnowledgeEngine
        _engine = KnowledgeEngine()
    return _engine


# ─── Response schemas ─────────────────────────────────────────────────

class KBStatusResponse(BaseModel):
    documents_dir: str
    available_pdfs: int
    loaded_pdfs: int
    indexed_terms: int
    registry_fields: int
    analytics_fields: int


class FieldLookupResponse(BaseModel):
    source_column: str
    target_field: str
    data_type: str
    date_format: Optional[str]
    confidence: float
    method: str
    description: str
    category: str
    use_in_analytics: bool
    wb_term: Optional[str]


class SearchResultResponse(BaseModel):
    document: str
    page_hint: int
    context: str
    score: float


# ─── Endpoints ────────────────────────────────────────────────────────

@router.get("/status", response_model=KBStatusResponse)
async def kb_status(_auth: dict = Depends(require_auth)):
    """Статус Knowledge Base."""
    reader = _get_reader()
    engine = _get_engine()
    r_stats = reader.stats()
    e_stats = engine.stats()
    return KBStatusResponse(
        documents_dir=r_stats["documents_dir"],
        available_pdfs=r_stats["available"],
        loaded_pdfs=r_stats["loaded"],
        indexed_terms=r_stats["indexed_terms"],
        registry_fields=e_stats["total_fields"],
        analytics_fields=e_stats["analytics_fields"],
    )


@router.get("/documents")
async def list_documents(_auth: dict = Depends(require_auth)):
    """Список PDF документов в knowledge_base/documents/."""
    reader = _get_reader()
    return reader.list_documents()


@router.post("/index")
async def reindex_documents(_auth: dict = Depends(require_auth)):
    """
    Переиндексировать все PDF в documents/.
    Вызывать после добавления нового документа.
    """
    reader = _get_reader()
    docs = reader.load_all()
    engine = _get_engine()
    enriched = reader.enrich_knowledge_engine(engine)
    index_path = reader.save_index()
    return {
        "indexed_documents": list(docs.keys()),
        "total_terms": reader.stats()["indexed_terms"],
        "engine_enriched_terms": enriched,
        "index_saved_to": str(index_path),
    }


@router.get("/search", response_model=list[SearchResultResponse])
async def search_documents(
    q: str = Query(..., description="Поисковый запрос"),
    limit: int = Query(5, ge=1, le=20),
    _auth: dict = Depends(require_auth),
):
    """Полнотекстовый поиск по PDF документам."""
    reader = _get_reader()
    if not reader.stats()["loaded"]:
        reader.load_all()
    results = reader.search(q, max_results=limit)
    return [
        SearchResultResponse(
            document=r.document,
            page_hint=r.page_hint,
            context=r.context,
            score=r.score,
        )
        for r in results
    ]


@router.get("/terms")
async def search_terms(
    q: str = Query(..., description="Термин для поиска"),
    _auth: dict = Depends(require_auth),
):
    """Поиск по извлечённым терминам из PDF."""
    reader = _get_reader()
    engine = _get_engine()
    # Ищем и в PDF индексе и в PDF движке
    pdf_results  = reader.search_terms(q)
    kb_results   = engine.search_pdf(q)
    seen = set()
    combined = []
    for r in pdf_results + kb_results:
        key = r["term"]
        if key not in seen:
            seen.add(key)
            combined.append(r)
    return combined[:10]


@router.get("/field", response_model=Optional[FieldLookupResponse])
async def lookup_field(
    col: str = Query(..., description="Название колонки из файла"),
    _auth: dict = Depends(require_auth),
):
    """Найти поле по названию колонки через Knowledge Engine."""
    engine = _get_engine()
    result = engine.lookup(col)
    if result is None:
        return None
    return FieldLookupResponse(
        source_column=result.source_column,
        target_field=result.target_field,
        data_type=result.data_type,
        date_format=result.date_format,
        confidence=result.confidence,
        method=result.method,
        description=result.description,
        category=result.category,
        use_in_analytics=result.use_in_analytics,
        wb_term=result.wb_term,
    )


@router.get("/categories")
async def get_categories(_auth: dict = Depends(require_auth)):
    """Все категории полей с количеством."""
    engine = _get_engine()
    stats = engine.stats()
    return stats["by_category"]
