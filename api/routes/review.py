"""
routes/review.py — Review Queue endpoints для Dashboard.

GET  /review              — pending items (для Dashboard)
POST /review/{id}/approve — пользователь одобрил
POST /review/{id}/reject  — пользователь исправил
GET  /review/stats        — статистика очереди
POST /review/apply/{hash} — применить все approved для hash
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_auth
from api.deps import get_review_queue, get_redis_client, get_storage
from review_queue.queue_store import ReviewQueue, ReviewItem
from worker.queue_client import RedisQueueClient
from worker.task_models import make_apply_reviews_task

router = APIRouter(prefix="/review", tags=["review"])


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
    filename: str
    status: str
    sample_values: list
    correct_field: Optional[str] = None
    resolved_by: Optional[str] = None


class ApproveRequest(BaseModel):
    field: Optional[str] = None   # None → принять suggested


class RejectRequest(BaseModel):
    correct_field: str


class ReviewStatsResponse(BaseModel):
    total: int
    pending: int
    by_status: dict[str, int]


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
        filename=item.filename,
        status=item.status,
        sample_values=item.sample_values,
        correct_field=item.correct_field,
        resolved_by=item.resolved_by,
    )


@router.get("", response_model=list[ReviewItemResponse])
async def get_pending_reviews(
    struct_hash: Optional[str] = None,
    _auth: dict = Depends(require_auth),
    queue: ReviewQueue = Depends(get_review_queue),
):
    """
    Возвращает pending items отсортированные по confidence (низший первым).
    Dashboard показывает их пользователю для подтверждения.
    """
    items = queue.get_pending(struct_hash=struct_hash)
    return [_item_to_response(i) for i in items]


@router.post("/{item_id}/approve", response_model=ReviewItemResponse)
async def approve_review(
    item_id: str,
    body: ApproveRequest,
    _auth: dict = Depends(require_auth),
    queue: ReviewQueue = Depends(get_review_queue),
):
    """Пользователь одобрил suggested_field (или выбрал другой)."""
    resolved = queue.approve(item_id, field=body.field, resolved_by="user")
    if not resolved:
        raise HTTPException(status_code=404, detail=f"Review item {item_id!r} not found")
    return _item_to_response(resolved)


@router.post("/{item_id}/reject", response_model=ReviewItemResponse)
async def reject_review(
    item_id: str,
    body: RejectRequest,
    _auth: dict = Depends(require_auth),
    queue: ReviewQueue = Depends(get_review_queue),
):
    """Пользователь исправил на correct_field."""
    resolved = queue.reject(item_id, correct_field=body.correct_field, resolved_by="user")
    if not resolved:
        raise HTTPException(status_code=404, detail=f"Review item {item_id!r} not found")
    return _item_to_response(resolved)


@router.get("/stats", response_model=ReviewStatsResponse)
async def get_review_stats(
    _auth: dict = Depends(require_auth),
    queue: ReviewQueue = Depends(get_review_queue),
):
    s = queue.stats()
    return ReviewStatsResponse(**s)


@router.post("/apply/{struct_hash}")
async def apply_reviews(
    struct_hash: str,
    _auth: dict = Depends(require_auth),
    redis: RedisQueueClient = Depends(get_redis_client),
):
    """
    Отправляет задачу APPLY_REVIEWS в worker queue.
    Worker применит все approved/rejected items к маппингу.
    """
    task = make_apply_reviews_task(struct_hash)
    task_id = redis.enqueue(task)
    return {
        "task_id": task_id,
        "struct_hash": struct_hash,
        "status": "queued",
        "message": "Review decisions will be applied by worker",
    }
