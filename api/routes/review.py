"""
routes/review.py — Review Queue endpoints для Dashboard.

GET  /review              — pending items (для Dashboard)
POST /review/{id}/approve — пользователь одобрил → авто-apply если все готовы
POST /review/{id}/reject  — пользователь исправил → авто-apply если все готовы
GET  /review/stats        — статистика очереди
POST /review/apply/{hash} — применить все approved/rejected для hash + записать в маппинг
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from api.auth import require_auth
from api.deps import get_review_queue, get_storage
from review_queue.queue_store import ReviewQueue, ReviewItem
from review_queue.mapping_bridge import apply_review_decisions
from mapping.mapping_storage import MappingStorage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/review", tags=["review"])


# ── Schemas ───────────────────────────────────────────────────────────

class ReviewItemResponse(BaseModel):
    id: str
    struct_hash: str
    source_column: str
    suggested_field: Optional[str]
    suggested_type: str
    confidence_score: float
    confidence_level: str
    match_method: str
    runner_up_field: Optional[str]
    runner_up_score: float
    filepath: str
    filename: str
    status: str
    created_at: str
    sample_values: list
    correct_field: Optional[str] = None
    resolved_by: Optional[str] = None


class ApplyResultResponse(BaseModel):
    struct_hash: str
    applied_fields: int
    reprocess_status: str    # "queued" | "no_file" | "skipped"
    message: str


class ApproveRequest(BaseModel):
    field: Optional[str] = None   # None → принять suggested


class RejectRequest(BaseModel):
    correct_field: str


class ReviewStatsResponse(BaseModel):
    total: int
    pending: int
    by_status: dict


# ── Helpers ───────────────────────────────────────────────────────────

def _item_to_response(item: ReviewItem) -> ReviewItemResponse:
    return ReviewItemResponse(
        id=item.id,
        struct_hash=item.struct_hash,
        source_column=item.source_column,
        suggested_field=item.suggested_field,
        suggested_type=item.suggested_type,
        confidence_score=item.confidence_score,
        confidence_level=item.confidence_level,
        match_method=item.match_method,
        runner_up_field=item.runner_up_field,
        runner_up_score=item.runner_up_score,
        filepath=item.filepath,
        filename=item.filename,
        status=item.status,
        created_at=item.created_at,
        sample_values=item.sample_values,
        correct_field=item.correct_field,
        resolved_by=item.resolved_by,
    )


def _all_resolved_for_hash(struct_hash: str, queue: ReviewQueue) -> bool:
    """True если все items для данного hash уже approved/rejected (нет pending)."""
    pending = queue.get_pending(struct_hash=struct_hash)
    return len(pending) == 0


def _do_apply(struct_hash: str, queue: ReviewQueue, storage: MappingStorage) -> dict:
    """
    1. Применяет approved/rejected решения к маппингу в storage.
    2. Ищет оригинальный файл в processed/ и копирует в incoming/ для повторной обработки.
    """
    applied = apply_review_decisions(struct_hash, queue, storage)

    # Найти оригинальный файл — берём filepath из первого resolved item
    reprocess_status = "no_file"
    all_items = queue.get_all()
    source_file = None
    for item in all_items:
        if item.struct_hash == struct_hash and item.filepath:
            source_file = Path(item.filepath)
            break

    if source_file:
        from config.settings import INCOMING_DIR, PROCESSED_DIR
        # Файл мог быть перемещён в processed/ после первой обработки
        candidates = [
            source_file,
            PROCESSED_DIR / source_file.name,
        ]
        for candidate in candidates:
            if candidate.exists():
                dest = INCOMING_DIR / source_file.name
                shutil.copy2(str(candidate), str(dest))
                logger.info(f"[review] Copied {candidate.name} → incoming/ for reprocessing")
                reprocess_status = "queued"
                break

    return {
        "struct_hash": struct_hash,
        "applied_fields": applied,
        "reprocess_status": reprocess_status,
        "message": (
            f"Applied {applied} field corrections. "
            f"File {'queued for reprocessing' if reprocess_status == 'queued' else 'not found for reprocessing'}."
        )
    }


# ── Routes ────────────────────────────────────────────────────────────

@router.get("", response_model=list[ReviewItemResponse])
async def get_pending_reviews(
    struct_hash: Optional[str] = None,
    _auth: dict = Depends(require_auth),
    queue: ReviewQueue = Depends(get_review_queue),
):
    """Pending items, сортировка по confidence (низший первым)."""
    items = queue.get_pending(struct_hash=struct_hash)
    return [_item_to_response(i) for i in items]


# ВАЖНО: /stats и /apply/ РАНЬШЕ /{item_id}/ чтобы FastAPI не перехватил как item_id
@router.get("/stats", response_model=ReviewStatsResponse)
async def get_review_stats(
    _auth: dict = Depends(require_auth),
    queue: ReviewQueue = Depends(get_review_queue),
):
    s = queue.stats()
    return ReviewStatsResponse(**s)


@router.post("/apply/{struct_hash}", response_model=ApplyResultResponse)
async def apply_reviews(
    struct_hash: str,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(require_auth),
    queue: ReviewQueue = Depends(get_review_queue),
    storage: MappingStorage = Depends(get_storage),
):
    """
    Применяет все approved/rejected решения для данного struct_hash.
    Обновляет маппинг в storage и копирует файл в incoming/ для повторной обработки.
    Вызывается фронтендом кнопкой «Применить решения».
    """
    result = _do_apply(struct_hash, queue, storage)
    return ApplyResultResponse(**result)


@router.post("/{item_id}/approve", response_model=ReviewItemResponse)
async def approve_review(
    item_id: str,
    body: ApproveRequest,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(require_auth),
    queue: ReviewQueue = Depends(get_review_queue),
    storage: MappingStorage = Depends(get_storage),
):
    """
    Пользователь одобрил suggested_field (или выбрал другой).
    Если после этого для данного struct_hash не осталось pending — авто-apply.
    """
    resolved = queue.approve(item_id, field=body.field, resolved_by="user")
    if not resolved:
        raise HTTPException(status_code=404, detail=f"Review item {item_id!r} not found")

    # Авто-apply когда все items для этого hash решены
    if _all_resolved_for_hash(resolved.struct_hash, queue):
        logger.info(f"[review] All items resolved for {resolved.struct_hash} — auto-applying")
        background_tasks.add_task(_do_apply, resolved.struct_hash, queue, storage)

    return _item_to_response(resolved)


@router.post("/{item_id}/reject", response_model=ReviewItemResponse)
async def reject_review(
    item_id: str,
    body: RejectRequest,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(require_auth),
    queue: ReviewQueue = Depends(get_review_queue),
    storage: MappingStorage = Depends(get_storage),
):
    """
    Пользователь исправил на correct_field.
    Если после этого для данного struct_hash не осталось pending — авто-apply.
    """
    resolved = queue.reject(item_id, correct_field=body.correct_field, resolved_by="user")
    if not resolved:
        raise HTTPException(status_code=404, detail=f"Review item {item_id!r} not found")

    if _all_resolved_for_hash(resolved.struct_hash, queue):
        logger.info(f"[review] All items resolved for {resolved.struct_hash} — auto-applying")
        background_tasks.add_task(_do_apply, resolved.struct_hash, queue, storage)

    return _item_to_response(resolved)
