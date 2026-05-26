"""
type_detector.py — автоматическое определение типов данных из sample значений.

Возвращает: DataTypeResult с detected_type и confidence.

Порядок проверок:
    1. Все NULL/NaN → unknown
    2. Уже pandas datetime → date
    3. Паттерны дат (regex)
    4. Boolean паттерны
    5. Целые числа
    6. Float (включая форматы "1 234,56")
    7. Default → str
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

# ─── Паттерны ───────────────────────────────────────────────────────
_DATE_PATTERNS = [
    re.compile(r"^\d{2}[.\-/]\d{2}[.\-/]\d{4}$"),           # DD.MM.YYYY
    re.compile(r"^\d{4}[.\-/]\d{2}[.\-/]\d{2}$"),           # YYYY-MM-DD
    re.compile(r"^\d{2}[.\-/]\d{2}[.\-/]\d{2}$"),           # DD.MM.YY
    re.compile(r"^\d{4}[.\-/]\d{2}[.\-/]\d{2}T\d{2}:\d{2}"),# ISO 8601
    re.compile(r"^\d{2}[.\-/]\d{2}[.\-/]\d{4}\s+\d{2}:\d{2}"),# DD.MM.YYYY HH:MM
    re.compile(r"^\w+\s+\d{4}$"),                            # Январь 2024
    re.compile(r"^\d{4}-W\d{2}$"),                           # 2024-W01 (iso week)
]

_BOOL_TRUE  = {"1", "yes", "да", "true", "истина", "y", "д", "+", "активен", "active"}
_BOOL_FALSE = {"0", "no", "нет", "false", "ложь",  "n", "н", "-", "неактивен", "inactive"}
_BOOL_ALL = _BOOL_TRUE | _BOOL_FALSE

_FLOAT_CLEAN_RE = re.compile(r"[\s₽$€%]")
_KNOWN_DATE_FIELDS = {"date", "дата", "период", "месяц"}


@dataclass
class DataTypeResult:
    detected_type: str      # str | int | float | date | bool
    confidence: float       # 0.0 – 1.0
    sample_size: int
    valid_count: int
    format_hint: Optional[str] = None   # для дат: "%d.%m.%Y"


def _is_null(v: Any) -> bool:
    if v is None:
        return True
    try:
        return pd.isna(v)
    except (TypeError, ValueError):
        return False


def _clean_numeric(s: str) -> str:
    """Убирает пробелы, символы валют, заменяет запятую на точку."""
    s = _FLOAT_CLEAN_RE.sub("", s)
    s = s.replace(",", ".")
    # Если точек > 1 — убираем все кроме последней
    parts = s.split(".")
    if len(parts) > 2:
        s = "".join(parts[:-1]) + "." + parts[-1]
    return s


def detect_type(
    values: list[Any],
    column_name: str = "",
    sample_size: int = 50,
) -> DataTypeResult:
    """
    Определяет тип данных по выборке значений.

    Args:
        values: список значений из колонки
        column_name: имя колонки (помогает с подсказкой для дат)
        sample_size: сколько значений использовать

    Returns:
        DataTypeResult
    """
    sample = values[:sample_size]
    non_null = [v for v in sample if not _is_null(v)]
    total = len(non_null)

    if total == 0:
        return DataTypeResult("str", 0.0, len(sample), 0)

    str_sample = [str(v).strip() for v in non_null]

    # ── 1. Уже pandas Timestamp ──────────────────────────────────────
    ts_count = sum(1 for v in non_null if isinstance(v, (pd.Timestamp,)))
    if ts_count / total >= 0.8:
        return DataTypeResult("date", round(ts_count / total, 3), len(sample), ts_count)

    # ── 2. Date patterns ─────────────────────────────────────────────
    date_hits = 0
    date_format_hint = None
    for s in str_sample:
        for pattern in _DATE_PATTERNS:
            if pattern.match(s):
                date_hits += 1
                break

    if date_hits / total >= 0.7:
        # Определяем формат-подсказку
        first = str_sample[0]
        if re.match(r"\d{2}\.\d{2}\.\d{4}", first):
            date_format_hint = "%d.%m.%Y"
        elif re.match(r"\d{4}-\d{2}-\d{2}", first):
            date_format_hint = "%Y-%m-%d"
        elif re.match(r"\d{2}/\d{2}/\d{4}", first):
            date_format_hint = "%d/%m/%Y"
        else:
            date_format_hint = "auto"
        return DataTypeResult(
            "date",
            round(date_hits / total, 3),
            len(sample), date_hits,
            format_hint=date_format_hint,
        )

    # Подсказка из названия колонки
    col_lower = column_name.lower()
    if any(kw in col_lower for kw in _KNOWN_DATE_FIELDS):
        # Дополнительная проверка через pandas
        try:
            pd_parsed = pd.to_datetime(pd.Series(str_sample[:20]), errors="coerce")
            valid_dates = pd_parsed.notna().sum()
            if valid_dates / min(20, total) >= 0.7:
                return DataTypeResult(
                    "date",
                    round(valid_dates / min(20, total), 3),
                    len(sample), int(valid_dates),
                    format_hint="auto",
                )
        except Exception:
            pass

    # ── 3. Boolean ───────────────────────────────────────────────────
    bool_hits = sum(1 for s in str_sample if s.lower() in _BOOL_ALL)
    if bool_hits / total >= 0.8:
        return DataTypeResult("bool", round(bool_hits / total, 3), len(sample), bool_hits)

    # ── 4. Integer ───────────────────────────────────────────────────
    int_hits = 0
    for s in str_sample:
        cleaned = _clean_numeric(s)
        # Убираем знак минуса для проверки
        check = cleaned.lstrip("-")
        if check.isdigit() and check:
            int_hits += 1

    if int_hits / total >= 0.85:
        return DataTypeResult("int", round(int_hits / total, 3), len(sample), int_hits)

    # ── 5. Float ─────────────────────────────────────────────────────
    float_hits = 0
    for s in str_sample:
        cleaned = _clean_numeric(s)
        try:
            float(cleaned)
            float_hits += 1
        except (ValueError, TypeError):
            pass

    if float_hits / total >= 0.75:
        return DataTypeResult("float", round(float_hits / total, 3), len(sample), float_hits)

    # ── 6. Default: str ──────────────────────────────────────────────
    return DataTypeResult("str", 1.0, len(sample), total)
