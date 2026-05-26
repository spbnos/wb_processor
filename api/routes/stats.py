"""
routes/stats.py — системная статистика и health.

GET /stats/health    — health check
GET /stats/system    — общая статистика (маппинги, очереди, файлы)
GET /stats/pipeline  — статус pipeline
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import require_auth
from api.deps import get_storage, get_review_queue, get_redis_client

router = APIRouter(prefix="/stats", tags=["stats"])


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0"
    phase: str = "Phase2-AsyncInfra"


class SystemStatsResponse(BaseModel):
    mappings: dict
    review_queue: dict
    redis_queues: dict


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Public endpoint — нет auth."""
    return HealthResponse(status="ok")


@router.get("/system", response_model=SystemStatsResponse)
async def system_stats(
    _auth: dict = Depends(require_auth),
    storage=Depends(get_storage),
    queue=Depends(get_review_queue),
    redis=Depends(get_redis_client),
):
    from mapping.mapping_repository import MappingRepository
    repo = MappingRepository(storage)
    mapping_stats = repo.stats()
    queue_stats = queue.stats()
    redis_lengths = redis.queue_lengths()

    return SystemStatsResponse(
        mappings=mapping_stats,
        review_queue=queue_stats,
        redis_queues=redis_lengths,
    )
