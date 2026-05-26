"""
ml/training_pipeline.py — Training Pipeline для ML моделей.

Модели:
  1. AnomalyDetector  — IsolationForest на sales features
                        цель: обнаружение аномальных продаж
  2. StockoutPredictor — LogisticRegression на stock + sales features
                         цель: предсказание риска stockout

Pipeline:
  1. Загрузить feature matrix из FeaturePipeline
  2. Подготовить X, y
  3. Train/eval split
  4. Обучить модель
  5. Оценить метрики
  6. Сохранить в ModelRegistry
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline as SKPipeline
from sklearn.metrics import (
    f1_score, precision_score, recall_score,
    roc_auc_score, average_precision_score,
)

from feature_store.feature_pipeline import FeaturePipeline
from ml.model_registry import ModelRegistry

logger = logging.getLogger(__name__)


# ─── Конфигурации моделей ────────────────────────────────────────────
ANOMALY_FEATURES = [
    "revenue_7d", "revenue_30d", "qty_sold_7d", "qty_sold_30d",
    "avg_price_30d", "order_count_30d", "revenue_trend_30d",
    "days_since_last_sale",
]

STOCKOUT_FEATURES = [
    "stock_qty_current", "stock_reserved_current",
    "stock_in_transit_current", "stockout_risk_score",
    "revenue_30d", "qty_sold_30d",
]


@dataclass
class TrainingResult:
    model_name: str
    version: str
    metrics: dict
    training_samples: int
    ok: bool
    error: Optional[str] = None


class AnomalyDetectorTrainer:
    """
    Обучает IsolationForest для обнаружения аномальных продаж.

    Unsupervised: метки не нужны.
    "Аномалия" = SKU с выбросами по паттернам продаж.
    """

    MODEL_NAME = "anomaly_detector"

    def __init__(
        self,
        contamination: float = 0.05,   # ~5% аномалий
        n_estimators: int = 100,
        random_state: int = 42,
    ):
        self._contamination = contamination
        self._n_estimators = n_estimators
        self._random_state = random_state

    def train(
        self,
        feature_matrix: pd.DataFrame,
        registry: ModelRegistry,
    ) -> TrainingResult:
        """
        Args:
            feature_matrix: DataFrame (index=sku, columns=features)
            registry: ModelRegistry для сохранения

        Returns:
            TrainingResult
        """
        available = [f for f in ANOMALY_FEATURES if f in feature_matrix.columns]
        if len(available) < 3:
            return TrainingResult(
                model_name=self.MODEL_NAME,
                version="", metrics={}, training_samples=0,
                ok=False,
                error=f"Too few features: need 3+, got {len(available)}",
            )

        X = feature_matrix[available].fillna(0.0)
        n_samples = len(X)

        if n_samples < 10:
            return TrainingResult(
                model_name=self.MODEL_NAME,
                version="", metrics={}, training_samples=n_samples,
                ok=False,
                error=f"Too few samples: need 10+, got {n_samples}",
            )

        # Пайплайн: scale → IsolationForest
        model = SKPipeline([
            ("scaler", StandardScaler()),
            ("clf", IsolationForest(
                contamination=self._contamination,
                n_estimators=self._n_estimators,
                random_state=self._random_state,
            )),
        ])
        model.fit(X)

        # Метрики для unsupervised: anomaly_rate, score_mean
        scores = model.named_steps["clf"].score_samples(
            model.named_steps["scaler"].transform(X)
        )
        preds = model.predict(X)  # +1 normal, -1 anomaly
        anomaly_rate = float((preds == -1).mean())

        metrics = {
            "anomaly_rate": round(anomaly_rate, 4),
            "score_mean": round(float(scores.mean()), 4),
            "score_std": round(float(scores.std()), 4),
            "n_anomalies": int((preds == -1).sum()),
            "n_normal": int((preds == 1).sum()),
            "features_used": len(available),
        }

        record = registry.save(
            model_name=self.MODEL_NAME,
            model_obj=model,
            metrics=metrics,
            params={
                "contamination": self._contamination,
                "n_estimators": self._n_estimators,
            },
            feature_set="sales_features",
            feature_names=available,
            training_samples=n_samples,
            description="IsolationForest anomaly detection on sales features",
        )

        logger.info(
            f"[trainer] {self.MODEL_NAME} {record.version}: "
            f"samples={n_samples} anomaly_rate={anomaly_rate:.3f}"
        )
        return TrainingResult(
            model_name=self.MODEL_NAME,
            version=record.version,
            metrics=metrics,
            training_samples=n_samples,
            ok=True,
        )


class StockoutPredictorTrainer:
    """
    Обучает LogisticRegression для предсказания риска stockout.

    Label: stockout_risk_score >= 0.7 → 1 (высокий риск)
    """

    MODEL_NAME = "stockout_predictor"

    def __init__(
        self,
        risk_threshold: float = 0.7,
        test_size: float = 0.2,
        random_state: int = 42,
        max_iter: int = 500,
    ):
        self._threshold = risk_threshold
        self._test_size = test_size
        self._random_state = random_state
        self._max_iter = max_iter

    def train(
        self,
        stock_matrix: pd.DataFrame,
        sales_matrix: Optional[pd.DataFrame],
        registry: ModelRegistry,
    ) -> TrainingResult:
        # Строим feature matrix
        df = self._build_features(stock_matrix, sales_matrix)
        if df is None:
            return TrainingResult(
                model_name=self.MODEL_NAME,
                version="", metrics={}, training_samples=0,
                ok=False, error="Cannot build feature matrix",
            )

        feature_cols = [c for c in STOCKOUT_FEATURES if c in df.columns and c != "stockout_risk_score"]
        if not feature_cols:
            return TrainingResult(
                model_name=self.MODEL_NAME,
                version="", metrics={}, training_samples=0,
                ok=False, error="No stockout features available",
            )

        if "stockout_risk_score" not in df.columns:
            return TrainingResult(
                model_name=self.MODEL_NAME,
                version="", metrics={}, training_samples=0,
                ok=False, error="stockout_risk_score missing (target column)",
            )

        X = df[feature_cols].fillna(0.0)
        y = (df["stockout_risk_score"] >= self._threshold).astype(int)
        n_samples = len(X)

        if n_samples < 20 or y.nunique() < 2:
            return TrainingResult(
                model_name=self.MODEL_NAME,
                version="", metrics={}, training_samples=n_samples,
                ok=False,
                error=f"Insufficient data: samples={n_samples} classes={y.nunique()}",
            )

        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=self._test_size,
            random_state=self._random_state, stratify=y,
        )

        model = SKPipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(
                max_iter=self._max_iter,
                random_state=self._random_state,
                class_weight="balanced",
            )),
        ])
        model.fit(X_tr, y_tr)

        y_pred = model.predict(X_te)
        y_proba = model.predict_proba(X_te)[:, 1]

        metrics = {
            "f1":        round(float(f1_score(y_te, y_pred, zero_division=0)), 4),
            "precision": round(float(precision_score(y_te, y_pred, zero_division=0)), 4),
            "recall":    round(float(recall_score(y_te, y_pred, zero_division=0)), 4),
            "roc_auc":   round(float(roc_auc_score(y_te, y_proba)), 4),
            "ap_score":  round(float(average_precision_score(y_te, y_proba)), 4),
            "pos_rate":  round(float(y.mean()), 4),
        }

        record = registry.save(
            model_name=self.MODEL_NAME,
            model_obj=model,
            metrics=metrics,
            params={
                "risk_threshold": self._threshold,
                "test_size": self._test_size,
                "max_iter": self._max_iter,
            },
            feature_set="stock_features",
            feature_names=feature_cols,
            training_samples=n_samples,
            description="LogisticRegression stockout risk predictor",
        )

        logger.info(
            f"[trainer] {self.MODEL_NAME} {record.version}: "
            f"f1={metrics['f1']:.3f} roc_auc={metrics['roc_auc']:.3f}"
        )
        return TrainingResult(
            model_name=self.MODEL_NAME,
            version=record.version,
            metrics=metrics,
            training_samples=n_samples,
            ok=True,
        )

    def _build_features(
        self,
        stock_matrix: pd.DataFrame,
        sales_matrix: Optional[pd.DataFrame],
    ) -> Optional[pd.DataFrame]:
        if stock_matrix.empty:
            return None
        df = stock_matrix.copy()
        if sales_matrix is not None and not sales_matrix.empty:
            # Мержим только те sales фичи которых нет в stock_matrix
            sales_cols = [
                c for c in STOCKOUT_FEATURES
                if c in sales_matrix.columns and c not in df.columns
            ]
            if sales_cols:
                df = df.join(sales_matrix[sales_cols], how="left")
        return df


class TrainingOrchestrator:
    """
    Оркестрирует обучение всех моделей.

    Использование:
        orch = TrainingOrchestrator()
        results = orch.run_all()
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        feature_pipeline: Optional[FeaturePipeline] = None,
    ):
        self._registry = registry or ModelRegistry()
        self._fp = feature_pipeline or FeaturePipeline()
        self._anomaly_trainer = AnomalyDetectorTrainer()
        self._stockout_trainer = StockoutPredictorTrainer()

    def run_all(self) -> list[TrainingResult]:
        """Обучает все модели последовательно."""
        logger.info("[orchestrator] Starting training run")
        results = []

        sales_matrix = self._fp.get_feature_matrix("sales_features")
        stock_matrix = self._fp.get_feature_matrix("stock_features")

        # Anomaly detector
        r1 = self._anomaly_trainer.train(sales_matrix, self._registry)
        results.append(r1)

        # Stockout predictor
        r2 = self._stockout_trainer.train(stock_matrix, sales_matrix, self._registry)
        results.append(r2)

        ok = sum(1 for r in results if r.ok)
        logger.info(f"[orchestrator] Done: {ok}/{len(results)} models trained successfully")
        return results

    def train_anomaly(self) -> TrainingResult:
        sales_matrix = self._fp.get_feature_matrix("sales_features")
        return self._anomaly_trainer.train(sales_matrix, self._registry)

    def train_stockout(self) -> TrainingResult:
        stock_matrix = self._fp.get_feature_matrix("stock_features")
        sales_matrix = self._fp.get_feature_matrix("sales_features")
        return self._stockout_trainer.train(stock_matrix, sales_matrix, self._registry)
