"""
review_queue/queue_store.py

Очередь маппингов требующих подтверждения.

Хранит FieldDecision с confidence NEEDS_REVIEW или LOW_CONF.
API/Dashboard читает эту очередь и показывает пользователю.
После подтверждения — запись удаляется, решение фиксируется в LearningStore.

Ключ: (struct_hash, source_column)
Backend: JSON (dev) / PostgreSQL (prod)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_QUEUE_PATH = Path(__file__).resolve().parent.parent / "data" / "review_queue.json"


class ReviewStatus(Enum):
    PENDING   = "pending"    # ждёт подтверждения
    APPROVED  = "approved"   # пользователь принял
    REJECTED  = "rejected"   # пользователь исправил
    EXPIRED   = "expired"    # файл уже обработан без подтверждения


@dataclass
class ReviewItem:
    id: str                       # uuid-like: "{struct_hash}::{source_column}"
    struct_hash: str
    source_column: str
    suggested_field: Optional[str]
    suggested_type: str
    confidence_score: float
    confidence_level: str         # needs_review / low_conf
    match_method: str             # как был найден (fuzzy_token, alias_exact, ...)
    runner_up_field: Optional[str]
    runner_up_score: float
    filepath: str
    filename: str
    status: str = ReviewStatus.PENDING.value
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None   # "user" | "auto_timeout"
    correct_field: Optional[str] = None # финальное поле после resolve
    sample_values: list = field(default_factory=list)


class ReviewQueue:
    """
    Использование:
        queue = ReviewQueue()

        # Добавить item
        queue.enqueue(item)

        # Получить все pending
        items = queue.get_pending()

        # Подтвердить
        queue.approve(item_id, field="sku")

        # Отклонить и исправить
        queue.reject(item_id, correct_field="barcode")
    """

    def __init__(self, use_db: bool = False, path: Path = _DEFAULT_QUEUE_PATH):
        self._use_db = use_db
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Enqueue ──────────────────────────────────────────

    def enqueue(self, item: ReviewItem) -> ReviewItem:
        """Добавляет или обновляет item в очереди."""
        existing = self.get_by_id(item.id)
        if existing and existing.status == ReviewStatus.PENDING.value:
            # Обновляем confidence если тот же ключ пришёл снова
            existing.confidence_score = item.confidence_score
            existing.created_at = item.created_at
            self._save_item(existing)
            return existing

        self._save_item(item)
        logger.info(
            f"[review_queue] Enqueued: {item.source_column!r} → "
            f"{item.suggested_field!r} ({item.confidence_score:.2f})"
        )
        return item

    def enqueue_many(self, items: list[ReviewItem]) -> list[ReviewItem]:
        return [self.enqueue(i) for i in items]

    # ── Get ──────────────────────────────────────────────

    def get_by_id(self, item_id: str) -> Optional[ReviewItem]:
        for r in self._load():
            if r["id"] == item_id:
                return ReviewItem(**r)
        return None

    def get_pending(self, struct_hash: Optional[str] = None) -> list[ReviewItem]:
        items = [
            ReviewItem(**r) for r in self._load()
            if r["status"] == ReviewStatus.PENDING.value
        ]
        if struct_hash:
            items = [i for i in items if i.struct_hash == struct_hash]
        return sorted(items, key=lambda x: x.confidence_score)  # низший confidence первым

    def get_all(self, status: Optional[str] = None) -> list[ReviewItem]:
        items = [ReviewItem(**r) for r in self._load()]
        if status:
            items = [i for i in items if i.status == status]
        return items

    def count_pending(self) -> int:
        return sum(1 for r in self._load() if r["status"] == ReviewStatus.PENDING.value)

    # ── Resolve ──────────────────────────────────────────

    def approve(
        self,
        item_id: str,
        field: Optional[str] = None,
        resolved_by: str = "user",
    ) -> Optional[ReviewItem]:
        """
        Пользователь одобрил suggested_field (или выбрал другой).
        field=None → принять suggested_field как есть.
        """
        item = self.get_by_id(item_id)
        if not item:
            logger.warning(f"[review_queue] Item {item_id!r} not found")
            return None
        item.status = ReviewStatus.APPROVED.value
        item.resolved_at = datetime.now(timezone.utc).isoformat()
        item.resolved_by = resolved_by
        item.correct_field = field or item.suggested_field
        self._save_item(item)
        logger.info(f"[review_queue] Approved: {item.source_column!r} → {item.correct_field!r}")
        return item

    def reject(
        self,
        item_id: str,
        correct_field: str,
        resolved_by: str = "user",
    ) -> Optional[ReviewItem]:
        """Пользователь исправил на correct_field."""
        item = self.get_by_id(item_id)
        if not item:
            return None
        item.status = ReviewStatus.REJECTED.value
        item.resolved_at = datetime.now(timezone.utc).isoformat()
        item.resolved_by = resolved_by
        item.correct_field = correct_field
        self._save_item(item)
        logger.info(
            f"[review_queue] Rejected: {item.source_column!r} "
            f"was {item.suggested_field!r} → corrected to {correct_field!r}"
        )
        return item

    def expire_for_hash(self, struct_hash: str):
        """Помечает все pending items для данного hash как expired."""
        data = self._load()
        count = 0
        for r in data:
            if r["struct_hash"] == struct_hash and r["status"] == ReviewStatus.PENDING.value:
                r["status"] = ReviewStatus.EXPIRED.value
                r["resolved_at"] = datetime.now(timezone.utc).isoformat()
                r["resolved_by"] = "auto_timeout"
                count += 1
        self._save_raw(data)
        if count:
            logger.info(f"[review_queue] Expired {count} items for hash={struct_hash}")

    # ── Stats ────────────────────────────────────────────

    def stats(self) -> dict:
        data = self._load()
        by_status: dict[str, int] = {}
        for r in data:
            s = r.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total": len(data),
            "by_status": by_status,
            "pending": by_status.get(ReviewStatus.PENDING.value, 0),
        }

    # ── JSON backend ─────────────────────────────────────

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            content = self._path.read_text(encoding="utf-8").strip()
            return json.loads(content) if content else []
        except (json.JSONDecodeError, ValueError):
            return []

    def _save_raw(self, data: list[dict]):
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _save_item(self, item: ReviewItem):
        data = self._load()
        updated = False
        for i, r in enumerate(data):
            if r["id"] == item.id:
                data[i] = asdict(item)
                updated = True
                break
        if not updated:
            data.append(asdict(item))
        self._save_raw(data)
