"""
Normalizer — чистит и приводит типы данных в ParseResult.df.

Задачи:
  - str  → strip, пустые → None
  - int  → int, нечисловые → None + warn
  - float → float, запятая→точка, пробелы убрать
  - date → datetime, пробует несколько форматов
  - bool → True/False
  - убирает дубли если есть уникальный ключ
  - обрезает строки длиннее лимита
"""
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from mapping.mapping_storage import MappingObj, MappingFieldObj
from parsers.parser_engine import ParseResult

logger = logging.getLogger(__name__)

_MAX_STR_LEN = 512
_BOOL_TRUE  = {"1", "yes", "да", "true", "истина", "y"}
_BOOL_FALSE = {"0", "no",  "нет", "false", "ложь",  "n"}


@dataclass
class NormalizeResult:
    df: pd.DataFrame
    filepath: Path
    row_count: int
    type_errors: dict = field(default_factory=dict)   # {column: count_of_errors}
    warnings: list = field(default_factory=list)
    ok: bool = True


class Normalizer:
    """
    Принимает ParseResult, возвращает NormalizeResult с чистым DataFrame.

    Использование:
        norm = Normalizer()
        result = norm.normalize(parse_result, mapping)
    """

    def normalize(self, parse_result: ParseResult, mapping: MappingObj) -> NormalizeResult:
        if not parse_result.ok or parse_result.df.empty:
            return NormalizeResult(
                df=parse_result.df,
                filepath=parse_result.filepath,
                row_count=0,
                warnings=parse_result.warnings + ["Skipped normalization: parse failed"],
                ok=False,
            )

        df = parse_result.df.copy()
        type_errors: dict = {}
        warnings = list(parse_result.warnings)

        # Строим lookup: target_field → MappingFieldObj
        field_lookup: dict[str, MappingFieldObj] = {
            f.target_field: f for f in mapping.fields
            if f.target_field != "ignore"
        }

        for col in df.columns:
            fm = field_lookup.get(col)
            if fm is None:
                logger.debug(f"[normalizer] No field config for col '{col}', skip")
                continue

            errors = 0
            dtype = fm.data_type

            if dtype == "str":
                df[col], errors = self._normalize_str(df[col])
            elif dtype == "int":
                df[col], errors = self._normalize_int(df[col])
            elif dtype == "float":
                df[col], errors = self._normalize_float(df[col])
            elif dtype == "date":
                df[col], errors = self._normalize_date(df[col], fm.date_format)
            elif dtype == "bool":
                df[col], errors = self._normalize_bool(df[col])
            else:
                logger.warning(f"[normalizer] Unknown dtype '{dtype}' for col '{col}'")

            if errors:
                type_errors[col] = errors
                warnings.append(
                    f"Колонка '{col}' ({dtype}): {errors} значений не удалось привести к типу"
                )

        # Убираем строки где все значения None
        before = len(df)
        df = df.dropna(how="all").reset_index(drop=True)
        dropped = before - len(df)
        if dropped:
            logger.info(f"[normalizer] Dropped {dropped} fully-empty rows")

        logger.info(f"[normalizer] Done: {len(df)} rows, {len(type_errors)} cols with type errors")

        return NormalizeResult(
            df=df,
            filepath=parse_result.filepath,
            row_count=len(df),
            type_errors=type_errors,
            warnings=warnings,
            ok=True,
        )

    # ── Типы ─────────────────────────────────────────────

    @staticmethod
    def _normalize_str(series: pd.Series) -> tuple[pd.Series, int]:
        errors = 0
        def clean(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            s = str(v).strip()
            if not s:
                return None
            return s[:_MAX_STR_LEN]
        return series.map(clean), errors

    @staticmethod
    def _normalize_int(series: pd.Series) -> tuple[pd.Series, int]:
        errors = 0
        result = []
        for v in series:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                result.append(None)
                continue
            try:
                # Убираем пробелы и символы валют
                cleaned = re.sub(r"[^\d\-]", "", str(v).strip().split(".")[0])
                result.append(int(cleaned) if cleaned and cleaned != "-" else None)
            except (ValueError, TypeError):
                result.append(None)
                errors += 1
        return pd.Series(result, dtype="Int64"), errors   # nullable Int64

    @staticmethod
    def _normalize_float(series: pd.Series) -> tuple[pd.Series, int]:
        errors = 0
        result = []
        for v in series:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                result.append(None)
                continue
            try:
                s = str(v).strip()
                # Формат "1 234,56" → "1234.56"
                s = re.sub(r"\s", "", s)            # убираем пробелы
                s = s.replace(",", ".")             # запятая → точка
                s = re.sub(r"[^\d.\-]", "", s)     # убираем всё лишнее
                # Если несколько точек — оставляем только последнюю
                parts = s.split(".")
                if len(parts) > 2:
                    s = "".join(parts[:-1]) + "." + parts[-1]
                result.append(float(s) if s and s not in (".", "-") else None)
            except (ValueError, TypeError):
                result.append(None)
                errors += 1
        return pd.Series(result, dtype="Float64"), errors

    @staticmethod
    def _normalize_date(series: pd.Series, date_format: Optional[str]) -> tuple[pd.Series, int]:
        errors = 0

        if date_format == "auto" or not date_format:
            # pandas умный — пробует сам
            converted = pd.to_datetime(series, errors="coerce", dayfirst=True)
            errors = int(converted.isna().sum()) - int(series.isna().sum())
            errors = max(errors, 0)
            return converted, errors

        # Пробуем указанный формат, потом fallback список
        fallback_formats = [
            date_format,
            "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y",
            "%d.%m.%Y %H:%M", "%Y-%m-%dT%H:%M:%S",
            "%d.%m.%Y %H:%M:%S",
        ]

        result = pd.Series([None] * len(series), dtype="object")

        for fmt in fallback_formats:
            mask = result.isna() & series.notna()
            if not mask.any():
                break
            try:
                partial = pd.to_datetime(series[mask], format=fmt, errors="coerce")
                result[mask] = partial
            except Exception:
                continue

        # Считаем ошибки: непустые значения где результат всё равно NaT
        original_notnull = series.notna()
        result_nat = pd.to_datetime(result, errors="coerce").isna()
        errors = int((original_notnull & result_nat).sum())

        return pd.to_datetime(result, errors="coerce"), errors

    @staticmethod
    def _normalize_bool(series: pd.Series) -> tuple[pd.Series, int]:
        errors = 0
        result = []
        for v in series:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                result.append(None)
                continue
            s = str(v).strip().lower()
            if s in _BOOL_TRUE:
                result.append(True)
            elif s in _BOOL_FALSE:
                result.append(False)
            else:
                result.append(None)
                errors += 1
        return pd.Series(result, dtype="boolean"), errors
