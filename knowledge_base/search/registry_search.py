"""
registry_search.py — поиск полей WB по названию колонки.

Логика:
  1. Точное совпадение с ключом реестра
  2. Точное совпадение с aliases[]
  3. Fuzzy matching через rapidfuzz
  4. Поиск по описанию (description)

Возвращает: RegistryMatch с target, type, description, score
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "registry" / "wb_field_registry.json"


@dataclass
class RegistryMatch:
    source_column: str       # исходная колонка
    target_field: str        # target из реестра
    data_type: str           # int / float / str / date / bool
    date_format: Optional[str]
    category: str            # product / finance / commission / ...
    description: str
    use_in_analytics: bool
    score: float             # 1.0 = точное, 0.0 = не найдено
    method: str              # exact / alias / fuzzy / description


class RegistrySearch:
    """
    Поиск по Knowledge Base реестру WB полей.

    Использование:
        searcher = RegistrySearch()
        match = searcher.search("Код номенклатуры")
        print(match.target_field)  # → "sku"
        print(match.score)         # → 1.0
    """

    def __init__(self, registry_path: Path = _REGISTRY_PATH):
        self._path = registry_path
        self._registry: dict = {}
        self._alias_map: dict[str, str] = {}   # alias_lower → original_key
        self._load()

    def _load(self):
        if not self._path.exists():
            logger.warning(f"[registry_search] Registry not found: {self._path}")
            return
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        self._registry = data.get("fields", {})

        # Строим reverse alias map
        for key, field in self._registry.items():
            self._alias_map[key.lower().strip()] = key
            for alias in field.get("aliases", []):
                self._alias_map[alias.lower().strip()] = key

        logger.debug(f"[registry_search] Loaded {len(self._registry)} fields, {len(self._alias_map)} aliases")

    def search(self, column: str) -> Optional[RegistryMatch]:
        """Ищет поле по названию колонки. Возвращает None если не найдено."""
        if not self._registry:
            return None

        col_lower = column.lower().strip()

        # 1. Точное совпадение с ключом
        if col_lower in self._alias_map:
            key = self._alias_map[col_lower]
            return self._make_match(column, key, 1.0, "exact")

        # 2. Fuzzy matching
        try:
            from rapidfuzz import process, fuzz
            best = process.extractOne(
                col_lower,
                list(self._alias_map.keys()),
                scorer=fuzz.token_sort_ratio,
                score_cutoff=70,
            )
            if best:
                matched_alias, score_raw, _ = best
                key = self._alias_map[matched_alias]
                return self._make_match(column, key, round(score_raw / 100, 3), "fuzzy")
        except ImportError:
            pass

        # 3. Substring match
        for alias_lower, key in self._alias_map.items():
            if col_lower in alias_lower or alias_lower in col_lower:
                if len(col_lower) >= 4:
                    ratio = len(col_lower) / max(len(alias_lower), 1)
                    score = 0.65 * (0.5 + 0.5 * ratio)
                    return self._make_match(column, key, round(score, 3), "substring")

        return None

    def search_many(self, columns: list[str]) -> dict[str, Optional[RegistryMatch]]:
        return {col: self.search(col) for col in columns}

    def get_field(self, target_field: str) -> Optional[dict]:
        """Получить полное описание поля по target_field."""
        for key, field in self._registry.items():
            if field.get("target") == target_field:
                return {**field, "_key": key}
        return None

    def list_by_category(self, category: str) -> list[dict]:
        return [
            {**v, "_key": k}
            for k, v in self._registry.items()
            if v.get("category") == category
        ]

    def analytics_fields(self) -> list[str]:
        """Все target_field которые используются в аналитике."""
        return [v["target"] for v in self._registry.values() if v.get("use_in_analytics")]

    def stats(self) -> dict:
        by_cat: dict[str, int] = {}
        analytics = 0
        for v in self._registry.values():
            cat = v.get("category", "unknown")
            by_cat[cat] = by_cat.get(cat, 0) + 1
            if v.get("use_in_analytics"):
                analytics += 1
        return {
            "total_fields": len(self._registry),
            "analytics_fields": analytics,
            "by_category": by_cat,
        }

    def _make_match(self, source: str, key: str, score: float, method: str) -> RegistryMatch:
        field = self._registry[key]
        return RegistryMatch(
            source_column=source,
            target_field=field["target"],
            data_type=field.get("type", "str"),
            date_format=field.get("date_format"),
            category=field.get("category", "unknown"),
            description=field.get("description", ""),
            use_in_analytics=field.get("use_in_analytics", False),
            score=score,
            method=method,
        )
