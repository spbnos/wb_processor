"""
knowledge_base/kb_engine.py

Движок базы знаний WB платформы.

Возможности:
  1. Поиск по JSON реестрам полей WB
  2. Чтение PDF документов (оферта, инструкции)
  3. Обогащение alias_dictionary новыми алиасами из реестра
  4. API для SmartMapper: get_field_info(column_name)

Используется SmartMapper для точного маппинга WB-специфичных колонок.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_KB_DIR = Path(__file__).resolve().parent
_FIELDS_DIR = _KB_DIR / "wb_fields"
_DOCS_DIR   = _KB_DIR / "documents"


# ─────────────────────────────────────────────────────────
class FieldInfo:
    def __init__(self, data: dict, source_column: str):
        self.source_column   = source_column
        self.target_field    = data.get("target_field", "ignore")
        self.data_type       = data.get("data_type", "str")
        self.date_format     = data.get("date_format")
        self.description     = data.get("description", "")
        self.aliases         = data.get("aliases", [])
        self.confidence      = 0.99   # из реестра = максимальный confidence


# ─────────────────────────────────────────────────────────
class KnowledgeBase:
    """
    Центральная база знаний платформы.

    Использование:
        kb = KnowledgeBase()
        info = kb.get_field_info("Код номенклатуры")
        # info.target_field == "sku", info.confidence == 0.99
    """

    def __init__(self):
        self._registries: dict[str, dict] = {}   # {registry_name: parsed_json}
        self._alias_index: dict[str, FieldInfo] = {}  # normalized_alias → FieldInfo
        self._load_all_registries()

    # ── Load ─────────────────────────────────────────────

    def _load_all_registries(self):
        """Загружает все JSON реестры из wb_fields/."""
        _FIELDS_DIR.mkdir(parents=True, exist_ok=True)
        _DOCS_DIR.mkdir(parents=True, exist_ok=True)

        for path in _FIELDS_DIR.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self._registries[path.stem] = data
                self._index_registry(path.stem, data)
                logger.info(f"[kb] Loaded registry: {path.name} ({len(data.get('fields', {}))} fields)")
            except Exception as e:
                logger.error(f"[kb] Failed to load {path.name}: {e}")

    def _index_registry(self, name: str, data: dict):
        """Строит быстрый индекс alias → FieldInfo."""
        fields = data.get("fields", {})
        for column_name, field_data in fields.items():
            info = FieldInfo(field_data, column_name)
            # Индексируем по оригинальному имени колонки
            key = self._normalize(column_name)
            if key:
                self._alias_index[key] = info
            # Индексируем по всем алиасам
            for alias in field_data.get("aliases", []):
                akey = self._normalize(alias)
                if akey:
                    self._alias_index[akey] = info

    # ── Search ───────────────────────────────────────────

    def get_field_info(self, column_name: str) -> Optional[FieldInfo]:
        """
        Точный поиск колонки в базе знаний.
        Возвращает FieldInfo если нашёл, None если нет.
        """
        key = self._normalize(column_name)
        if key in self._alias_index:
            return self._alias_index[key]

        # Частичный поиск — ищем подстроку
        for indexed_key, info in self._alias_index.items():
            if key in indexed_key or indexed_key in key:
                if len(min(key, indexed_key, key=len)) >= 4:  # минимум 4 символа
                    return info

        return None

    def search(self, query: str, top_k: int = 5) -> list[tuple[float, FieldInfo]]:
        """
        Полнотекстовый поиск по базе знаний.
        Возвращает список (score, FieldInfo) отсортированный по релевантности.
        """
        q = self._normalize(query)
        results: list[tuple[float, FieldInfo]] = []
        seen_targets: set[str] = set()

        for key, info in self._alias_index.items():
            if info.target_field in seen_targets:
                continue
            score = self._similarity(q, key)
            if score > 0.3:
                results.append((score, info))
                seen_targets.add(info.target_field)

        results.sort(key=lambda x: x[0], reverse=True)
        return results[:top_k]

    def get_all_target_fields(self) -> dict[str, str]:
        """Возвращает все target_field → description из реестров."""
        result: dict[str, str] = {}
        for registry in self._registries.values():
            for col, data in registry.get("fields", {}).items():
                tf = data.get("target_field", "")
                if tf and tf not in result:
                    result[tf] = data.get("description", "")
        return result

    def stats(self) -> dict:
        return {
            "registries": list(self._registries.keys()),
            "total_indexed": len(self._alias_index),
            "total_target_fields": len(self.get_all_target_fields()),
            "documents": [p.name for p in _DOCS_DIR.glob("*") if p.is_file()],
        }

    # ── PDF reading ──────────────────────────────────────

    def read_pdf(self, filename: str) -> str:
        """Читает текст из PDF документа в documents/."""
        path = _DOCS_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {filename}")
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n".join(text_parts)
        except ImportError:
            # Fallback: pypdf2
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(str(path))
                return "\n".join(
                    page.extract_text() or ""
                    for page in reader.pages
                )
            except ImportError:
                raise ImportError(
                    "Install PDF reader: pip install pdfplumber"
                )

    def search_in_pdf(self, filename: str, query: str, context_chars: int = 300) -> list[str]:
        """
        Ищет query в PDF и возвращает релевантные отрывки.
        Используется для поиска определений в оферте WB.
        """
        text = self.read_pdf(filename)
        q_lower = query.lower()
        results = []
        pos = 0
        while True:
            idx = text.lower().find(q_lower, pos)
            if idx == -1:
                break
            start = max(0, idx - context_chars // 2)
            end = min(len(text), idx + len(query) + context_chars // 2)
            snippet = text[start:end].strip()
            results.append(snippet)
            pos = idx + 1
            if len(results) >= 5:
                break
        return results

    # ── Export to alias_dictionary ───────────────────────

    def export_aliases_for_smartmapper(self) -> dict[str, list[str]]:
        """
        Экспортирует алиасы из KB в формат для alias_dictionary.py.
        Возвращает {target_field: [aliases]}.
        """
        result: dict[str, list[str]] = {}
        for key, info in self._alias_index.items():
            tf = info.target_field
            if tf not in result:
                result[tf] = []
            if key not in result[tf]:
                result[tf].append(key)
        return result

    # ── Helpers ──────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        t = str(text).lower().strip()
        t = re.sub(r"[^\w\s]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """Простая мера схожести строк."""
        if a == b:
            return 1.0
        if not a or not b:
            return 0.0
        # Общие слова
        words_a = set(a.split())
        words_b = set(b.split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)
