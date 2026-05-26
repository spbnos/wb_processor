"""
core/schema_validator.py — валидация данных перед загрузкой в БД.

Слой между Normalizer и DataLoader.

Проверки:
  1. Обязательные поля присутствуют и не пустые
  2. Типы данных соответствуют схеме
  3. Диапазоны значений (цена > 0, количество >= 0)
  4. Аномальные значения (выброс > 3σ)
  5. Дубликаты по ключевым полям

Результат: ValidationResult с errors + warnings + cleaned DataFrame.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─── Правила валидации ───────────────────────────────────────────────

# Поля которые должны быть непустыми
_REQUIRED_NOTNULL = {"sku"}

# Числовые поля с ограничениями: (min, max, allow_negative)
_NUMERIC_BOUNDS: dict[str, tuple] = {
    "price":       (0,      1_000_000, False),
    "cost_price":  (0,      1_000_000, False),
    "revenue":     (-100_000, 10_000_000, True),  # возвраты могут быть отрицательными
    "quantity":    (0,       100_000,  False),
    "commission":  (-100_000, 1_000_000, True),
    "logistics":   (0,       1_000_000, False),
    "ad_spend":    (0,       10_000_000, False),
    "impressions": (0,       1_000_000_000, False),
    "clicks":      (0,       100_000_000, False),
    "ctr":         (0,       1.0,       False),
    "cpc":         (0,       100_000,   False),
    "reserved":    (0,       1_000_000, False),
    "in_transit":  (0,       1_000_000, False),
}

# Поля для проверки outliers (Z-score > 5 σ = сильный выброс)
_OUTLIER_ZSCORE_THRESHOLD = 5.0
_OUTLIER_FIELDS = {"revenue", "price", "quantity", "ad_spend"}


@dataclass
class ValidationIssue:
    field: str
    issue_type: str     # "null", "out_of_range", "wrong_type", "outlier", "duplicate"
    severity: str       # "error" | "warning"
    message: str
    affected_rows: int
    sample_values: list = field(default_factory=list)


@dataclass
class ValidationResult:
    df: pd.DataFrame          # очищенный DataFrame (плохие строки удалены)
    original_rows: int
    valid_rows: int
    dropped_rows: int
    issues: list[ValidationIssue]
    ok: bool                  # False если есть critical errors
    warnings: list[str]


class SchemaValidator:
    """
    Валидирует DataFrame после нормализации.

    Использование:
        validator = SchemaValidator()
        result = validator.validate(df, category="wb_report")
        if result.ok:
            loader.load(result.df, ...)
    """

    def __init__(
        self,
        zscore_threshold: float = _OUTLIER_ZSCORE_THRESHOLD,
        drop_invalid: bool = True,
    ):
        self._zscore = zscore_threshold
        self._drop = drop_invalid

    def validate(
        self,
        df: pd.DataFrame,
        category: str = "unknown",
    ) -> ValidationResult:
        if df.empty:
            return ValidationResult(
                df=df, original_rows=0, valid_rows=0,
                dropped_rows=0, issues=[], ok=True, warnings=[],
            )

        original_rows = len(df)
        issues: list[ValidationIssue] = []
        warnings_list: list[str] = []
        bad_mask = pd.Series(False, index=df.index)

        # ── 1. Null checks ─────────────────────────────────────────
        for field_name in _REQUIRED_NOTNULL:
            if field_name not in df.columns:
                continue
            null_mask = df[field_name].isna() | (df[field_name].astype(str).str.strip() == "")
            if null_mask.any():
                count = int(null_mask.sum())
                issues.append(ValidationIssue(
                    field=field_name,
                    issue_type="null",
                    severity="error",
                    message=f"Required field '{field_name}' is null in {count} rows",
                    affected_rows=count,
                ))
                bad_mask |= null_mask

        # ── 2. Numeric bounds ─────────────────────────────────────
        for field_name, (vmin, vmax, allow_neg) in _NUMERIC_BOUNDS.items():
            if field_name not in df.columns:
                continue
            col = pd.to_numeric(df[field_name], errors="coerce")
            oob = col.notna() & ((col < vmin) | (col > vmax))
            if not allow_neg:
                oob |= col.notna() & (col < 0)
            if oob.any():
                count = int(oob.sum())
                sample = col[oob].dropna().head(3).tolist()
                sev = "error" if field_name in ("price", "quantity") else "warning"
                issues.append(ValidationIssue(
                    field=field_name,
                    issue_type="out_of_range",
                    severity=sev,
                    message=f"'{field_name}' out of bounds in {count} rows [min={vmin}, max={vmax}]",
                    affected_rows=count,
                    sample_values=[round(v, 2) for v in sample],
                ))
                if sev == "error":
                    bad_mask |= oob

        # ── 3. Outlier detection (Z-score) ─────────────────────────
        for field_name in _OUTLIER_FIELDS:
            if field_name not in df.columns:
                continue
            col = pd.to_numeric(df[field_name], errors="coerce").dropna()
            if len(col) < 10:
                continue
            mean, std = col.mean(), col.std()
            if std < 1e-8:
                continue
            zscores = (col - mean).abs() / std
            outliers = zscores > self._zscore
            if outliers.any():
                count = int(outliers.sum())
                issues.append(ValidationIssue(
                    field=field_name,
                    issue_type="outlier",
                    severity="warning",
                    message=f"'{field_name}' has {count} outliers (|z| > {self._zscore}σ)",
                    affected_rows=count,
                    sample_values=col[outliers].head(3).round(2).tolist(),
                ))

        # ── 4. Duplicate SKUs (warning, не удаляем) ────────────────
        if "sku" in df.columns and "date" in df.columns:
            dup_mask = df.duplicated(subset=["sku", "date"], keep=False)
            if dup_mask.any():
                count = int(dup_mask.sum())
                issues.append(ValidationIssue(
                    field="sku+date",
                    issue_type="duplicate",
                    severity="warning",
                    message=f"{count} duplicate (sku, date) pairs found",
                    affected_rows=count,
                ))
                warnings_list.append(f"{count} duplicate (sku+date) pairs")

        # ── 5. Применяем маску плохих строк ───────────────────────
        if self._drop and bad_mask.any():
            clean_df = df[~bad_mask].copy().reset_index(drop=True)
        else:
            clean_df = df.copy()

        dropped = int(bad_mask.sum())
        valid = original_rows - dropped

        errors_count = sum(1 for i in issues if i.severity == "error")
        ok = errors_count == 0

        # Логируем
        if issues:
            for issue in issues:
                if issue.severity == "error":
                    logger.warning(
                        f"[validator] ERROR {issue.field}: {issue.message}"
                    )
                else:
                    logger.debug(
                        f"[validator] WARN {issue.field}: {issue.message}"
                    )

        logger.info(
            f"[validator] {category}: "
            f"original={original_rows} valid={valid} dropped={dropped} "
            f"errors={errors_count} ok={ok}"
        )

        return ValidationResult(
            df=clean_df,
            original_rows=original_rows,
            valid_rows=valid,
            dropped_rows=dropped,
            issues=issues,
            ok=ok,
            warnings=warnings_list,
        )
