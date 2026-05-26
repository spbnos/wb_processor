"""
knowledge_base/search/knowledge_engine.py

Движок поиска по реестру WB полей.

Возможности:
  1. Точный поиск по названию колонки
  2. Fuzzy поиск (rapidfuzz) по aliases + названию
  3. Поиск по target_field
  4. Фильтрация по категории
  5. PDF документы (оферта WB) — извлечение и поиск

Используется SmartMapper вместо alias_dictionary как PRIMARY источник.
alias_dictionary остаётся fallback для общих полей.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "registry" / "wb_field_registry.json"
_DOCUMENTS_DIR = Path(__file__).resolve().parents[1] / "documents"


# ─────────────────────────────────────────────────────────
# Результат поиска
# ─────────────────────────────────────────────────────────
@dataclass
class FieldLookupResult:
    source_column: str          # как в файле
    target_field: str           # что это значит
    data_type: str              # str/int/float/date/bool
    date_format: Optional[str]  # для дат
    confidence: float           # 0.0 – 1.0
    method: str                 # exact / alias / fuzzy / pdf
    description: str            # человекочитаемое описание
    category: str               # product/finance/commission/...
    use_in_analytics: bool      # нужно ли для ML/аналитики
    wb_term: Optional[str] = None  # WB-специфичный термин если есть


# ─────────────────────────────────────────────────────────
# KnowledgeEngine
# ─────────────────────────────────────────────────────────
class KnowledgeEngine:
    """
    Главный класс поиска по базе знаний WB.

    Использование:
        engine = KnowledgeEngine()
        result = engine.lookup("Код номенклатуры")
        # result.target_field == "sku", result.confidence == 1.0
    """

    def __init__(self, registry_path: Path = _REGISTRY_PATH):
        self._registry_path = registry_path
        self._registry: dict = {}
        self._alias_index: dict[str, str] = {}   # alias_lower → column_name
        self._target_index: dict[str, list[str]] = {}  # target → [column_names]
        self._pdf_index: dict[str, str] = {}     # term_lower → description
        self._load()
        self._load_saved_pdf_index()

    def _load(self):
        if not self._registry_path.exists():
            logger.warning(f"[kb] Registry not found: {self._registry_path}")
            return

        with open(self._registry_path, encoding="utf-8") as f:
            data = json.load(f)

        self._registry = data.get("fields", {})

        # Строим alias index
        for col_name, field_data in self._registry.items():
            col_lower = col_name.lower().strip()
            self._alias_index[col_lower] = col_name

            for alias in field_data.get("aliases", []):
                self._alias_index[alias.lower().strip()] = col_name

            target = field_data.get("target", "")
            if target not in self._target_index:
                self._target_index[target] = []
            self._target_index[target].append(col_name)

        logger.info(
            f"[kb] Loaded {len(self._registry)} fields, "
            f"{len(self._alias_index)} aliases"
        )

    def _load_saved_pdf_index(self) -> None:
        """Термины оферты из registry/pdf_index.json (без перечитывания PDF)."""
        index_path = self._registry_path.parent / "pdf_index.json"
        if not index_path.exists():
            return
        try:
            with open(index_path, encoding="utf-8") as f:
                data = json.load(f)
            terms = data.get("terms", {})
            if isinstance(terms, dict):
                self._pdf_index.update(terms)
                logger.info(f"[kb] PDF index: {len(terms)} terms from {index_path.name}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[kb] Cannot load pdf_index.json: {e}")

    def lookup(self, column: str) -> Optional[FieldLookupResult]:
        """
        Ищет поле по названию колонки.
        Порядок: exact → alias → fuzzy.
        Возвращает None если ничего не найдено с confidence > 0.3.
        """
        if not self._registry:
            return None

        norm = column.lower().strip()
        # Убираем спецсимволы для сравнения
        norm_clean = re.sub(r"[,\.\(\)%/]", " ", norm).strip()
        norm_clean = re.sub(r"\s+", " ", norm_clean)

        # 1. Exact match
        if norm in self._alias_index:
            col_name = self._alias_index[norm]
            return self._make_result(column, col_name, 1.0, "exact")

        # 2. Alias exact (после нормализации)
        if norm_clean in self._alias_index:
            col_name = self._alias_index[norm_clean]
            return self._make_result(column, col_name, 0.97, "alias_exact")

        # 3. Substring match в ключах реестра
        for reg_col_lower, reg_col_name in self._alias_index.items():
            if norm in reg_col_lower or reg_col_lower in norm:
                score = len(min(norm, reg_col_lower, key=len)) / len(max(norm, reg_col_lower, key=len))
                if score > 0.7:
                    return self._make_result(column, reg_col_name, round(0.85 * score, 3), "substring")

        # 4. Fuzzy match через rapidfuzz
        return self._fuzzy_lookup(column, norm)

    def _fuzzy_lookup(self, original: str, norm: str) -> Optional[FieldLookupResult]:
        try:
            from rapidfuzz import fuzz, process

            choices = list(self._alias_index.keys())
            match = process.extractOne(
                norm, choices,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=65,
            )
            if match:
                matched_alias, score, _ = match
                col_name = self._alias_index[matched_alias]
                confidence = round(score / 100 * 0.82, 3)
                return self._make_result(original, col_name, confidence, "fuzzy")
        except ImportError:
            pass
        return None

    def _make_result(
        self,
        source_col: str,
        reg_col_name: str,
        confidence: float,
        method: str,
    ) -> FieldLookupResult:
        field_data = self._registry[reg_col_name]
        return FieldLookupResult(
            source_column=source_col,
            target_field=field_data.get("target", "unknown"),
            data_type=field_data.get("type", "str"),
            date_format=field_data.get("date_format"),
            confidence=confidence,
            method=method,
            description=field_data.get("description", ""),
            category=field_data.get("category", "unknown"),
            use_in_analytics=field_data.get("use_in_analytics", True),
            wb_term=field_data.get("wb_term"),
        )

    def lookup_many(self, columns: list[str]) -> dict[str, Optional[FieldLookupResult]]:
        return {col: self.lookup(col) for col in columns}

    def get_by_target(self, target_field: str) -> list[str]:
        """Все колонки которые маппятся в данный target_field."""
        return self._target_index.get(target_field, [])

    def get_by_category(self, category: str) -> dict[str, dict]:
        """Все поля заданной категории."""
        return {
            col: data for col, data in self._registry.items()
            if data.get("category") == category
        }

    def analytics_fields(self) -> list[str]:
        """target_field-ы которые нужны для аналитики/ML."""
        seen = set()
        result = []
        for data in self._registry.values():
            if data.get("use_in_analytics"):
                t = data.get("target", "")
                if t and t not in seen:
                    seen.add(t)
                    result.append(t)
        return result

    def stats(self) -> dict:
        total = len(self._registry)
        by_cat: dict[str, int] = {}
        analytics_count = 0
        for data in self._registry.values():
            cat = data.get("category", "unknown")
            by_cat[cat] = by_cat.get(cat, 0) + 1
            if data.get("use_in_analytics"):
                analytics_count += 1
        return {
            "total_fields": total,
            "analytics_fields": analytics_count,
            "service_fields": total - analytics_count,
            "aliases_indexed": len(self._alias_index),
            "by_category": by_cat,
            "pdf_terms": len(self._pdf_index),
        }

    # ─────────────────────────────────────────────────────
    # PDF поддержка — индексирование документов (оферта WB)
    # ─────────────────────────────────────────────────────

    def index_pdf(self, pdf_path: Path) -> int:
        """
        Читает PDF и добавляет термины в поисковый индекс.
        Возвращает кол-во извлечённых терминов.
        """
        if not pdf_path.exists():
            logger.warning(f"[kb] PDF not found: {pdf_path}")
            return 0

        text = self._extract_pdf_text(pdf_path)
        if not text:
            return 0

        terms = self._extract_wb_terms(text)
        self._pdf_index.update(terms)
        logger.info(f"[kb] Indexed {len(terms)} terms from {pdf_path.name}")
        return len(terms)

    def index_all_pdfs(self) -> int:
        """Индексирует все PDF из папки documents/."""
        if not _DOCUMENTS_DIR.exists():
            return 0
        total = 0
        for pdf in _DOCUMENTS_DIR.glob("*.pdf"):
            total += self.index_pdf(pdf)
        return total

    def search_pdf(self, query: str) -> list[dict]:
        """Поиск по PDF индексу."""
        q = query.lower().strip()
        results = []
        for term, definition in self._pdf_index.items():
            if q in term or q in definition.lower():
                results.append({"term": term, "definition": definition})
        return results[:10]

    @staticmethod
    def _extract_pdf_text(pdf_path: Path) -> str:
        """Извлекает текст из PDF. Требует pypdf или pdfplumber."""
        try:
            import pypdf
            reader = pypdf.PdfReader(str(pdf_path))
            return "\n".join(
                page.extract_text() or "" for page in reader.pages
            )
        except ImportError:
            pass
        try:
            import pdfplumber
            with pdfplumber.open(str(pdf_path)) as pdf:
                return "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )
        except ImportError:
            pass
        logger.warning("[kb] No PDF library. Install: pip install pypdf")
        return ""

    @staticmethod
    def _extract_wb_terms(text: str) -> dict[str, str]:
        """
        Извлекает WB-термины и их определения из текста оферты.
        Паттерны: 'Термин — определение', 'Термин: определение'
        """
        terms = {}
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if not line or len(line) < 10:
                continue
            # Паттерн: "Слово(а) — определение"
            for sep in [" — ", " - ", ": "]:
                if sep in line:
                    parts = line.split(sep, 1)
                    term = parts[0].strip()
                    definition = parts[1].strip() if len(parts) > 1 else ""
                    if 2 <= len(term.split()) <= 6 and len(definition) > 10:
                        terms[term.lower()] = definition[:200]
                        break
        return terms
