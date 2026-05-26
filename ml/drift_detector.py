"""
ml/drift_detector.py — мониторинг деградации модели (Model Drift Detection).

Два типа дрейфа:
  1. Data drift    — входные фичи изменились по сравнению с обучением
  2. Concept drift — метрики модели на новых данных ухудшились

Методы обнаружения:
  - PSI (Population Stability Index) для числовых фич
  - KS-test (Kolmogorov-Smirnov) для распределений
  - Метрические пороги (anomaly_rate отклонился > threshold)

Результат: DriftReport — сохраняется в data/drift_reports/
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from ml.model_registry import ModelRegistry

logger = logging.getLogger(__name__)

_REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "drift_reports"

# PSI thresholds: < 0.1 stable, 0.1-0.25 minor, > 0.25 major
PSI_STABLE  = 0.10
PSI_WARNING = 0.25

# Anomaly rate drift threshold
ANOMALY_RATE_DRIFT = 0.15   # если rate изменился > 15% — предупреждение


@dataclass
class FeatureDrift:
    feature_name: str
    psi: float
    ks_statistic: float
    ks_pvalue: float
    drift_level: str    # "stable" | "warning" | "critical"
    baseline_mean: float
    current_mean: float
    mean_shift_pct: float


@dataclass
class DriftReport:
    model_name: str
    version: str
    report_date: str
    data_drift_detected: bool
    concept_drift_detected: bool
    overall_severity: str         # "none" | "warning" | "critical"
    feature_drifts: list[FeatureDrift]
    baseline_metrics: dict
    current_metrics: dict
    recommendations: list[str]
    n_baseline_samples: int
    n_current_samples: int


class DriftDetector:
    """
    Использование:
        detector = DriftDetector()
        report = detector.detect(
            model_name="anomaly_detector",
            baseline_df=baseline_features,
            current_df=new_features,
            current_metrics={"anomaly_rate": 0.08},
        )
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        reports_dir: Path = _REPORTS_DIR,
    ):
        self._registry = registry or ModelRegistry()
        self._reports_dir = reports_dir
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def detect(
        self,
        model_name: str,
        baseline_df: pd.DataFrame,
        current_df: pd.DataFrame,
        current_metrics: Optional[dict] = None,
    ) -> DriftReport:
        """
        Проводит полный drift analysis.

        Args:
            model_name:      имя модели в реестре
            baseline_df:     DataFrame фич на момент обучения
            current_df:      DataFrame фич сейчас
            current_metrics: текущие метрики модели (опционально)

        Returns:
            DriftReport
        """
        record = self._registry.get_active_record(model_name)
        version = record.version if record else "unknown"
        baseline_metrics = record.metrics if record else {}
        feature_names = record.feature_names if record else list(baseline_df.columns)

        logger.info(
            f"[drift] Analyzing {model_name} {version}: "
            f"baseline={len(baseline_df)} current={len(current_df)}"
        )

        # ── Feature drift ─────────────────────────────────
        feature_drifts = []
        for fname in feature_names:
            if fname not in baseline_df.columns or fname not in current_df.columns:
                continue
            fd = self._analyze_feature(
                fname,
                baseline_df[fname].dropna().values,
                current_df[fname].dropna().values,
            )
            feature_drifts.append(fd)

        # ── Concept drift ─────────────────────────────────
        concept_drift = False
        if current_metrics and baseline_metrics:
            concept_drift = self._check_concept_drift(
                baseline_metrics, current_metrics, model_name
            )

        # ── Severity ──────────────────────────────────────
        data_drift = any(fd.drift_level != "stable" for fd in feature_drifts)
        critical = any(fd.drift_level == "critical" for fd in feature_drifts)
        severity = "none"
        if concept_drift or critical:
            severity = "critical"
        elif data_drift:
            severity = "warning"

        # ── Recommendations ───────────────────────────────
        recs = self._recommendations(severity, feature_drifts, concept_drift)

        report = DriftReport(
            model_name=model_name,
            version=version,
            report_date=datetime.now(timezone.utc).isoformat(),
            data_drift_detected=data_drift,
            concept_drift_detected=concept_drift,
            overall_severity=severity,
            feature_drifts=feature_drifts,
            baseline_metrics=baseline_metrics,
            current_metrics=current_metrics or {},
            recommendations=recs,
            n_baseline_samples=len(baseline_df),
            n_current_samples=len(current_df),
        )

        self._save_report(report)
        logger.info(
            f"[drift] Report: severity={severity} "
            f"data_drift={data_drift} concept_drift={concept_drift}"
        )
        return report

    def get_latest_report(self, model_name: str) -> Optional[DriftReport]:
        """Загружает последний отчёт для модели."""
        reports = list(self._reports_dir.glob(f"{model_name}_*.json"))
        if not reports:
            return None
        latest = max(reports, key=lambda p: p.stat().st_mtime)
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            fds = [FeatureDrift(**fd) for fd in data.pop("feature_drifts", [])]
            data["feature_drifts"] = fds
            return DriftReport(**data)
        except Exception as e:
            logger.error(f"[drift] Cannot load report: {e}")
            return None

    # ── Analysis ─────────────────────────────────────────

    @staticmethod
    def _analyze_feature(
        fname: str,
        baseline: np.ndarray,
        current: np.ndarray,
    ) -> FeatureDrift:
        if len(baseline) < 5 or len(current) < 5:
            return FeatureDrift(
                feature_name=fname, psi=0.0,
                ks_statistic=0.0, ks_pvalue=1.0,
                drift_level="stable",
                baseline_mean=float(baseline.mean()) if len(baseline) > 0 else 0.0,
                current_mean=float(current.mean()) if len(current) > 0 else 0.0,
                mean_shift_pct=0.0,
            )

        psi = DriftDetector._compute_psi(baseline, current)

        ks_stat, ks_pval = stats.ks_2samp(baseline, current)

        b_mean = float(baseline.mean())
        c_mean = float(current.mean())
        shift_pct = abs(c_mean - b_mean) / (abs(b_mean) + 1e-8) * 100

        if psi > PSI_WARNING or ks_pval < 0.01:
            level = "critical"
        elif psi > PSI_STABLE or ks_pval < 0.05:
            level = "warning"
        else:
            level = "stable"

        return FeatureDrift(
            feature_name=fname,
            psi=round(psi, 4),
            ks_statistic=round(float(ks_stat), 4),
            ks_pvalue=round(float(ks_pval), 4),
            drift_level=level,
            baseline_mean=round(b_mean, 4),
            current_mean=round(c_mean, 4),
            mean_shift_pct=round(shift_pct, 2),
        )

    @staticmethod
    def _compute_psi(baseline: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
        """Population Stability Index."""
        try:
            breakpoints = np.percentile(baseline, np.linspace(0, 100, bins + 1))
            breakpoints = np.unique(breakpoints)
            if len(breakpoints) < 2:
                return 0.0

            b_counts = np.histogram(baseline, bins=breakpoints)[0]
            c_counts = np.histogram(current, bins=breakpoints)[0]

            b_pct = (b_counts + 1e-6) / (len(baseline) + 1e-6)
            c_pct = (c_counts + 1e-6) / (len(current) + 1e-6)

            psi = float(np.sum((b_pct - c_pct) * np.log(b_pct / c_pct)))
            return abs(psi)
        except Exception:
            return 0.0

    @staticmethod
    def _check_concept_drift(
        baseline_metrics: dict,
        current_metrics: dict,
        model_name: str,
    ) -> bool:
        """Проверяет деградацию метрик."""
        if model_name == "anomaly_detector":
            b_rate = baseline_metrics.get("anomaly_rate", 0)
            c_rate = current_metrics.get("anomaly_rate", 0)
            return abs(c_rate - b_rate) > ANOMALY_RATE_DRIFT

        if model_name == "stockout_predictor":
            b_f1 = baseline_metrics.get("f1", 0)
            c_f1 = current_metrics.get("f1", 0)
            return (b_f1 - c_f1) > 0.10   # деградация F1 > 10%

        return False

    @staticmethod
    def _recommendations(
        severity: str,
        feature_drifts: list[FeatureDrift],
        concept_drift: bool,
    ) -> list[str]:
        recs = []
        if severity == "critical":
            recs.append("🔴 CRITICAL: Retrain model immediately")
        if concept_drift:
            recs.append("Model performance degraded — schedule retraining")
        critical_features = [fd.feature_name for fd in feature_drifts if fd.drift_level == "critical"]
        if critical_features:
            recs.append(f"Critical feature drift: {', '.join(critical_features)}")
        if severity == "warning":
            recs.append("🟡 Monitor closely, plan retraining within 7 days")
        if not recs:
            recs.append("🟢 Model stable, no action required")
        return recs

    def _save_report(self, report: DriftReport):
        fname = f"{report.model_name}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
        path = self._reports_dir / fname
        data = asdict(report)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug(f"[drift] Report saved: {path.name}")
