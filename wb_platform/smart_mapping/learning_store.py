"""
learning_store.py — персистентное хранилище решений SmartMapper.

Хранит историю авто-маппингов:
    (struct_hash, source_column) → (target_field, применено N раз, последний score)

Используется для:
    1. ConfidenceScorer.historical_hits
    2. Быстрый lookup известных комбинаций
    3. Постепенное улучшение quality со временем

Backend: JSON-файл (для dev/test) или PostgreSQL (для prod).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "learning_store.json"


@dataclass
class LearningRecord:
    struct_hash: str
    source_column: str
    target_field: str
    hits: int               # сколько раз применялось
    last_score: float
    confirmed: bool         # True если пользователь подтвердил
    last_seen: str          # ISO timestamp


class LearningStore:
    """
    use_db=False → JSON (тесты, dev)
    use_db=True  → PostgreSQL (prod, через SQLAlchemy)
    """

    def __init__(self, use_db: bool = False, path: Path = _DEFAULT_STORE_PATH):
        self._use_db = use_db
        self._path = path
        if not use_db:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Record ──────────────────────────────────────────────────────

    def record(
        self,
        struct_hash: str,
        source_column: str,
        target_field: str,
        score: float,
        confirmed: bool = False,
    ) -> LearningRecord:
        """Записывает или обновляет решение."""
        existing = self.get(struct_hash, source_column)
        now = datetime.now(timezone.utc).isoformat()

        if existing:
            existing.hits += 1
            existing.last_score = score
            existing.last_seen = now
            if confirmed:
                existing.confirmed = True
            self._save_record(existing)
            return existing

        record = LearningRecord(
            struct_hash=struct_hash,
            source_column=source_column,
            target_field=target_field,
            hits=1,
            last_score=score,
            confirmed=confirmed,
            last_seen=now,
        )
        self._save_record(record)
        logger.debug(f"[learning] New record: {source_column!r} → {target_field!r} (score={score:.3f})")
        return record

    # ── Get ─────────────────────────────────────────────────────────

    def get(self, struct_hash: str, source_column: str) -> Optional[LearningRecord]:
        """Возвращает запись по ключу (struct_hash, source_column)."""
        if self._use_db:
            return self._get_db(struct_hash, source_column)
        return self._get_json(struct_hash, source_column)

    def get_hits(self, struct_hash: str, source_column: str, target_field: str) -> int:
        """Быстро возвращает кол-во применений для конкретного маппинга."""
        rec = self.get(struct_hash, source_column)
        if rec and rec.target_field == target_field:
            return rec.hits
        return 0

    def get_all_for_hash(self, struct_hash: str) -> list[LearningRecord]:
        """Все записи для данного struct_hash (весь формат файла)."""
        if self._use_db:
            return self._get_all_db(struct_hash)
        data = self._load()
        return [
            LearningRecord(**r) for r in data
            if r["struct_hash"] == struct_hash
        ]

    # ── Stats ────────────────────────────────────────────────────────

    def stats(self) -> dict:
        data = self._load()
        confirmed = sum(1 for r in data if r.get("confirmed"))
        return {
            "total_records": len(data),
            "confirmed": confirmed,
            "auto": len(data) - confirmed,
        }

    # ── Confirmation ─────────────────────────────────────────────────

    def confirm(self, struct_hash: str, source_column: str):
        """Помечает решение как подтверждённое пользователем."""
        rec = self.get(struct_hash, source_column)
        if rec:
            rec.confirmed = True
            self._save_record(rec)

    def reject(self, struct_hash: str, source_column: str, correct_field: str, score: float = 1.0):
        """Исправляет неверное решение — увеличивает hits для правильного."""
        data = self._load()
        # Удаляем неверную запись
        data = [
            r for r in data
            if not (r["struct_hash"] == struct_hash and r["source_column"] == source_column)
        ]
        self._save_raw(data)
        # Записываем правильную
        self.record(struct_hash, source_column, correct_field, score, confirmed=True)

    # ── JSON backend ─────────────────────────────────────────────────

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            content = self._path.read_text(encoding="utf-8").strip()
            return json.loads(content) if content else []
        except (json.JSONDecodeError, ValueError):
            return []

    def _save_raw(self, data: list[dict]):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_record(self, record: LearningRecord):
        data = self._load()
        key = (record.struct_hash, record.source_column)
        updated = False
        for i, r in enumerate(data):
            if (r["struct_hash"], r["source_column"]) == key:
                data[i] = asdict(record)
                updated = True
                break
        if not updated:
            data.append(asdict(record))
        self._save_raw(data)

    def _get_json(self, struct_hash: str, source_column: str) -> Optional[LearningRecord]:
        for r in self._load():
            if r["struct_hash"] == struct_hash and r["source_column"] == source_column:
                return LearningRecord(**r)
        return None

    # ── DB backend (stub — реализуется в Фазе 2) ─────────────────────

    def _get_db(self, struct_hash: str, source_column: str) -> Optional[LearningRecord]:
        # TODO: SQLAlchemy query в Фазе 2
        raise NotImplementedError("DB backend coming in Phase 2")

    def _get_all_db(self, struct_hash: str) -> list[LearningRecord]:
        raise NotImplementedError("DB backend coming in Phase 2")
