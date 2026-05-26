"""
deps.py — FastAPI dependencies (shared across routes).
"""
from __future__ import annotations
import sys
from pathlib import Path
from functools import lru_cache

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_PLATFORM = Path(__file__).resolve().parents[2] / "wb_platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from mapping.mapping_storage import MappingStorage
from review_queue.queue_store import ReviewQueue
from worker.queue_client import RedisQueueClient


@lru_cache(maxsize=1)
def get_storage() -> MappingStorage:
    return MappingStorage(use_db=False)


@lru_cache(maxsize=1)
def get_review_queue() -> ReviewQueue:
    return ReviewQueue(use_db=False)


@lru_cache(maxsize=1)
def get_redis_client() -> RedisQueueClient:
    return RedisQueueClient(mock=True)  # mock до Docker
