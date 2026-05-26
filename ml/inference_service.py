"""
ml/inference_service.py — Inference Service.

Предоставляет предсказания по обученным моделям.

API (используется FastAPI роутером в api/routes/ml.py):
  predict_anomalies(skus)      → dict[sku, AnomalyResult]
  predict_stockout(skus)       → dict[sku, StockoutResult]
  predict_all(skus)            → dict[sku, SKUInsights]
  batch_predict(feature_df)    → DataFrame с предсказаниями

Кэширование: LRU cache на загрузку модели (не перезагружает на каждый запрос).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

from ml.model_registry import ModelRegistry
from feature_store.feature_pipeline import FeaturePipeline

logger = logging.getLogger(__name__)


# ─── Результаты инференса ────────────────────────────────────────────

@dataclass
class AnomalyResult:
    sku: str
    is_anomaly: bool
    anomaly_score: float       # чем меньше — тем аномальнее (IsolationForest)
    confidence: float          # 0.0–1.0
    explanation: str


@dataclass
class StockoutResult:
    sku: str
    stockout_risk: float       # 0.0–1.0
    high_risk: bool            # > threshold
    days_to_stockout: Optional[int]
    recommendation: str


@dataclass
class SKUInsights:
    sku: str
    anomaly: Optional[AnomalyResult] = None
    stockout: Optional[StockoutResult] = None
    features_used: dict = field(default_factory=dict)
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── InferenceService ────────────────────────────────────────────────

class InferenceService:
    """
    Использование:
        svc = InferenceService()
        insights = svc.predict_all(["ART001", "ART002"])
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        feature_pipeline: Optional[FeaturePipeline] = None,
        stockout_threshold: float = 0.5,
    ):
        self._registry = registry or ModelRegistry()
        self._fp = feature_pipeline or FeaturePipeline()
        self._stockout_threshold = stockout_threshold

        # Кэш загруженных моделей
        self._models: dict = {}

    def _get_model(self, name: str):
        """Ленивая загрузка с кэшированием."""
        if name not in self._models:
            model = self._registry.load(name)
            if model is None:
                logger.warning(f"[inference] Model not found: {name}")
            self._models[name] = model
        return self._models[name]

    def invalidate_cache(self):
        """Сбрасывает кэш моделей — вызывается после обучения новой версии."""
        self._models.clear()
        logger.info("[inference] Model cache invalidated")

    # ── Anomaly ──────────────────────────────────────────

    def predict_anomaly(self, sku: str) -> Optional[AnomalyResult]:
        features = self._fp.get_sku_features(sku, ["sales_features"])
        if not features:
            return None

        model = self._get_model("anomaly_detector")
        if model is None:
            return None

        record = self._registry.get_active_record("anomaly_detector")
        feature_names = record.feature_names if record else list(features.keys())

        X = pd.DataFrame([{f: features.get(f, 0.0) for f in feature_names}])
        X = X.fillna(0.0)

        try:
            pred = model.predict(X)[0]           # +1 normal, -1 anomaly
            score = model.score_samples(X)[0]    # anomaly score
        except Exception as e:
            logger.error(f"[inference] Anomaly predict error for {sku}: {e}")
            return None

        is_anomaly = bool(pred == -1)
        # Нормализуем score в 0–1 (больше = более нормальный)
        confidence = float(np.clip((score + 0.5) / 1.0, 0.0, 1.0))

        explanation = self._anomaly_explanation(features, is_anomaly)

        return AnomalyResult(
            sku=sku,
            is_anomaly=is_anomaly,
            anomaly_score=round(float(score), 4),
            confidence=round(confidence, 4),
            explanation=explanation,
        )

    def predict_anomalies(self, skus: list[str]) -> dict[str, AnomalyResult]:
        """Batch inference для списка SKU."""
        return {
            sku: result
            for sku in skus
            if (result := self.predict_anomaly(sku)) is not None
        }

    # ── Stockout ─────────────────────────────────────────

    def predict_stockout(self, sku: str) -> Optional[StockoutResult]:
        features = self._fp.get_sku_features(sku)
        if not features:
            return None

        model = self._get_model("stockout_predictor")
        if model is None:
            # Fallback: используем stockout_risk_score из feature store
            risk = features.get("stockout_risk_score", 0.0)
            return StockoutResult(
                sku=sku,
                stockout_risk=round(risk, 4),
                high_risk=risk >= self._stockout_threshold,
                days_to_stockout=self._estimate_days(features),
                recommendation=self._stockout_recommendation(risk, features),
            )

        record = self._registry.get_active_record("stockout_predictor")
        feature_names = record.feature_names if record else []
        X = pd.DataFrame([{f: features.get(f, 0.0) for f in feature_names}])
        X = X.fillna(0.0)

        try:
            risk = float(model.predict_proba(X)[0, 1])
        except Exception as e:
            logger.error(f"[inference] Stockout predict error for {sku}: {e}")
            risk = features.get("stockout_risk_score", 0.0)

        return StockoutResult(
            sku=sku,
            stockout_risk=round(risk, 4),
            high_risk=risk >= self._stockout_threshold,
            days_to_stockout=self._estimate_days(features),
            recommendation=self._stockout_recommendation(risk, features),
        )

    def predict_stockouts(self, skus: list[str]) -> dict[str, StockoutResult]:
        return {
            sku: result
            for sku in skus
            if (result := self.predict_stockout(sku)) is not None
        }

    # ── Combined ─────────────────────────────────────────

    def predict_all(self, skus: list[str]) -> dict[str, SKUInsights]:
        results: dict[str, SKUInsights] = {}
        for sku in skus:
            features = self._fp.get_sku_features(sku)
            insights = SKUInsights(
                sku=sku,
                anomaly=self.predict_anomaly(sku),
                stockout=self.predict_stockout(sku),
                features_used=features,
            )
            results[sku] = insights
        return results

    # ── Batch DataFrame ───────────────────────────────────

    def batch_predict_df(
        self,
        feature_df: pd.DataFrame,
        include_anomaly: bool = True,
        include_stockout: bool = True,
    ) -> pd.DataFrame:
        """
        Принимает feature matrix, возвращает DataFrame с предсказаниями.
        Используется для мониторинга и отчётов.
        """
        results = []
        for sku in feature_df.index:
            row = {"sku": str(sku)}
            features = feature_df.loc[sku].to_dict()

            if include_anomaly:
                model = self._get_model("anomaly_detector")
                if model:
                    record = self._registry.get_active_record("anomaly_detector")
                    fnames = record.feature_names if record else []
                    X = pd.DataFrame([{f: features.get(f, 0.0) for f in fnames}]).fillna(0.0)
                    try:
                        pred = model.predict(X)[0]
                        score = model.score_samples(X)[0]
                        row["is_anomaly"] = bool(pred == -1)
                        row["anomaly_score"] = round(float(score), 4)
                    except Exception:
                        row["is_anomaly"] = None
                        row["anomaly_score"] = None

            if include_stockout:
                model = self._get_model("stockout_predictor")
                if model:
                    record = self._registry.get_active_record("stockout_predictor")
                    fnames = record.feature_names if record else []
                    X = pd.DataFrame([{f: features.get(f, 0.0) for f in fnames}]).fillna(0.0)
                    try:
                        risk = float(model.predict_proba(X)[0, 1])
                        row["stockout_risk"] = round(risk, 4)
                        row["high_stockout_risk"] = risk >= self._stockout_threshold
                    except Exception:
                        row["stockout_risk"] = None
                        row["high_stockout_risk"] = None

            results.append(row)

        return pd.DataFrame(results).set_index("sku") if results else pd.DataFrame()

    # ── Helpers ───────────────────────────────────────────

    @staticmethod
    def _anomaly_explanation(features: dict, is_anomaly: bool) -> str:
        if not is_anomaly:
            return "Normal sales pattern"
        issues = []
        if features.get("revenue_7d", 0) == 0 and features.get("revenue_30d", 0) > 0:
            issues.append("no sales in last 7 days")
        if features.get("revenue_trend_30d", 0) < -1000:
            issues.append("sharp revenue decline")
        if features.get("days_since_last_sale", 0) > 14:
            issues.append("no sales for 14+ days")
        return "Anomaly: " + (", ".join(issues) if issues else "unusual pattern detected")

    @staticmethod
    def _estimate_days(features: dict) -> Optional[int]:
        qty = features.get("stock_qty_current", 0)
        qty_sold = features.get("qty_sold_30d", 0)
        if qty <= 0 or qty_sold <= 0:
            return None
        daily_rate = qty_sold / 30
        return max(0, int(qty / daily_rate))

    @staticmethod
    def _stockout_recommendation(risk: float, features: dict) -> str:
        qty = features.get("stock_qty_current", 0)
        sold_30d = features.get("qty_sold_30d", 0)
        if risk >= 0.8:
            return f"🔴 URGENT: Reorder immediately. Stock={qty:.0f}, sold 30d={sold_30d:.0f}"
        if risk >= 0.5:
            return f"🟡 WARNING: Plan reorder soon. Stock={qty:.0f}"
        return f"🟢 OK: Stock level sufficient. Risk={risk:.0%}"
