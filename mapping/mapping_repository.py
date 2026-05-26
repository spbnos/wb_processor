"""
MappingRepository — дополнительные запросы поверх MappingStorage.
Поиск по имени, категории, статистика, список с деталями.
"""
import logging
from typing import Optional

from mapping.mapping_storage import MappingStorage
from db.models import Mapping

logger = logging.getLogger(__name__)


class MappingRepository:
    def __init__(self, storage: MappingStorage):
        self._s = storage

    def find_by_name(self, name: str) -> Optional[Mapping]:
        """Поиск по точному имени (регистронезависимо)."""
        for m in self._s.get_all(active_only=False):
            if m.name.lower() == name.lower():
                return m
        return None

    def search(self, query: str) -> list[Mapping]:
        """Поиск по подстроке в имени или категории."""
        q = query.lower()
        return [
            m for m in self._s.get_all(active_only=False)
            if q in m.name.lower()
            or q in (m.category or "").lower()
            or q in (m.subcategory or "").lower()
        ]

    def list_by_category(self, category: str) -> list[Mapping]:
        return [
            m for m in self._s.get_all()
            if m.category == category
        ]

    def stats(self) -> dict:
        """Статистика по маппингам."""
        all_m = self._s.get_all(active_only=False)
        active = [m for m in all_m if m.is_active]
        by_cat: dict[str, int] = {}
        for m in active:
            by_cat[m.category] = by_cat.get(m.category, 0) + 1
        return {
            "total": len(all_m),
            "active": len(active),
            "inactive": len(all_m) - len(active),
            "by_category": by_cat,
        }

    def summary_list(self) -> list[dict]:
        """Список маппингов для CLI вывода."""
        return [
            {
                "id": m.id,
                "name": m.name,
                "category": m.category,
                "subcategory": m.subcategory or "—",
                "columns": m.column_count or 0,
                "active": m.is_active,
                "struct_hash": m.struct_hash,
            }
            for m in self._s.get_all(active_only=False)
        ]
