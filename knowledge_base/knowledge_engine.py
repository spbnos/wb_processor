"""
knowledge_base/knowledge_engine.py

Движок базы знаний платформы.

Источники:
  1. wb_fields/*.json       — эталонные справочники полей WB
  2. documents/             — PDF/DOCX документы (оферта, инструкции)
  3. Интернет (опционально) — поиск актуальных данных WB API

Используется:
  - SmartMapper          — вместо fuzzy matching → точный lookup
  - ColumnMatcher        — как дополнительный уровень L0 (highest priority)
  - Normalizer           — правильные типы данных из справочника
  - DataLoader           — правильные target_field для новых колонок
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_KB_DIR = Path(__file__).parent
_FIELDS_DIR = _KB_DIR / "wb_fields"
_DOCS_DIR   = _KB_DIR / "documents"


@dataclass
class FieldDefinition:
    """Определение поля из справочника."""
    source_column: str      # оригинальное название колонки
    target_field: str       # target_field в системе
    data_type: str          # str/int/float/date/bool
    date_format: Optional[str]
    description: str
    category: str
    priority: str           # primary / secondary
    confidence: float       # 1.0 для справочника (максимум)
    wb_field: Optional[str] # API имя поля WB
    source_registry: str    # из какого справочника


class KnowledgeEngine:
    """
    Загружает все справочники и отвечает на вопрос:
    'Что значит эта колонка?'

    Использование:
        engine = KnowledgeEngine()
        defn = engine.lookup('Код номенклатуры')
        # defn.target_field == 'sku', defn.confidence == 1.0
    """

    def __init__(self):
        self._registry: dict[str, FieldDefinition] = {}
        self._load_all_registries()

    def _load_all_registries(self):
        """Загружает все JSON справочники из wb_fields/."""
        _FIELDS_DIR.mkdir(parents=True, exist_ok=True)
        loaded = 0
        for json_path in _FIELDS_DIR.glob("*.json"):
            try:
                self._load_registry(json_path)
                loaded += 1
            except Exception as e:
                logger.warning(f"[kb] Cannot load {json_path.name}: {e}")
        logger.info(f"[kb] Loaded {loaded} registries, {len(self._registry)} field definitions")

    def _load_registry(self, path: Path):
        """Парсит один JSON справочник."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        registry_name = path.stem
        fields: dict = data.get("fields", {})

        for col_name, field_data in fields.items():
            defn = FieldDefinition(
                source_column=col_name,
                target_field=field_data.get("target", "ignore"),
                data_type=field_data.get("type", "str"),
                date_format=field_data.get("date_format"),
                description=field_data.get("description", ""),
                category=field_data.get("category", "unknown"),
                priority=field_data.get("priority", "primary"),
                confidence=1.0,   # справочник = максимальная уверенность
                wb_field=field_data.get("wb_field"),
                source_registry=registry_name,
            )
            # Храним по нормализованному ключу
            key = self._normalize(col_name)
            self._registry[key] = defn

    def lookup(self, column: str) -> Optional[FieldDefinition]:
        """
        Точный поиск по справочнику (нормализованный).
        Возвращает None если не найдено — тогда работает fuzzy matcher.
        """
        key = self._normalize(column)
        return self._registry.get(key)

    def lookup_all(self) -> dict[str, FieldDefinition]:
        """Все определения для построения alias list."""
        return self._registry.copy()

    def stats(self) -> dict:
        by_cat: dict[str, int] = {}
        by_target: dict[str, int] = {}
        for defn in self._registry.values():
            by_cat[defn.category] = by_cat.get(defn.category, 0) + 1
            by_target[defn.target_field] = by_target.get(defn.target_field, 0) + 1
        return {
            "total_fields": len(self._registry),
            "by_category": by_cat,
            "by_target_field": by_target,
            "registries": [p.stem for p in _FIELDS_DIR.glob("*.json")],
        }

    def search(self, query: str) -> list[FieldDefinition]:
        """Поиск по описанию — для UI справочника."""
        q = query.lower()
        results = []
        for defn in self._registry.values():
            if (q in defn.source_column.lower()
                    or q in defn.description.lower()
                    or q in defn.target_field.lower()
                    or q in defn.category.lower()):
                results.append(defn)
        return sorted(results, key=lambda d: d.target_field)

    @staticmethod
    def _normalize(text: str) -> str:
        """Нормализация для поиска."""
        return text.strip().lower()
