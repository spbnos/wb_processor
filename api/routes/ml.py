"""
routes/ml.py — ML inference endpoints.

GET  /ml/predict/anomaly/{sku}      — аномалии по одному SKU
POST /ml/predict/anomalies          — batch аномалии
GET  /ml/predict/stockout/{sku}     — stockout риск по SKU
POST /ml/predict/stockouts          — batch stockout
POST /ml/predict/all                — полные insights по списку SKU
GET  /ml/models                     — список моделей в registry
GET  /ml/models/{name}              — детали модели (версии, метрики)
POST /ml/train                      — запустить training через worker
GET  /ml/drift/{model_name}         — последний drift report
GET  /ml/features/stats             — статистика feature store
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_auth
from api.deps import get_storage

router = APIRouter(prefix="/ml", tags=["ml"])


# ─── Response schemas ────────────────────────────────────────────────

class AnomalyResponse(BaseModel):
    sku: str
    is_anomaly: bool
    anomaly_score: float
    confidence: float
    explanation: str


class StockoutResponse(BaseModel):
    sku: str
    stockout_risk: float
    high_risk: bool
    days_to_stockout: Optional[int]
    recommendation: str


class SKUInsightsResponse(BaseModel):
    sku: str
    anomaly: Optional[AnomalyResponse]
    stockout: Optional[StockoutResponse]
    computed_at: str


class ModelVersionResponse(BaseModel):
    model_name: str
    version: str
    status: str
    metrics: dict
    training_samples: int
    trained_at: str


class DriftReportResponse(BaseModel):
    model_name: str
    version: str
    overall_severity: str
    data_drift_detected: bool
    concept_drift_detected: bool
    n_drifted_features: int
    recommendations: list[str]
    report_date: str


class BatchSKURequest(BaseModel):
    skus: list[str]


class TrainRequest(BaseModel):
    models: list[str] = ["anomaly_detector", "stockout_predictor"]


# ─── Lazy-init InferenceService ──────────────────────────────────────
_inference_svc = None


def _get_inference():
    global _inference_svc
    if _inference_svc is None:
        from ml.inference_service import InferenceService
        _inference_svc = InferenceService()
    return _inference_svc


# ─── Endpoints ───────────────────────────────────────────────────────

@router.get("/predict/anomaly/{sku}", response_model=AnomalyResponse)
async def predict_anomaly(sku: str, _auth: dict = Depends(require_auth)):
    """Аномалия продаж для одного SKU."""
    svc = _get_inference()
    result = svc.predict_anomaly(sku)
    if result is None:
        raise HTTPException(404, f"No features found for SKU '{sku}'")
    return AnomalyResponse(
        sku=result.sku, is_anomaly=result.is_anomaly,
        anomaly_score=result.anomaly_score, confidence=result.confidence,
        explanation=result.explanation,
    )


@router.post("/predict/anomalies", response_model=dict)
async def predict_anomalies_batch(
    body: BatchSKURequest,
    _auth: dict = Depends(require_auth),
):
    """Batch аномалии для списка SKU."""
    svc = _get_inference()
    results = svc.predict_anomalies(body.skus)
    return {
        sku: {
            "is_anomaly": r.is_anomaly,
            "anomaly_score": r.anomaly_score,
            "confidence": r.confidence,
            "explanation": r.explanation,
        }
        for sku, r in results.items()
    }


@router.get("/predict/stockout/{sku}", response_model=StockoutResponse)
async def predict_stockout(sku: str, _auth: dict = Depends(require_auth)):
    """Stockout риск для одного SKU."""
    svc = _get_inference()
    result = svc.predict_stockout(sku)
    if result is None:
        raise HTTPException(404, f"No features found for SKU '{sku}'")
    return StockoutResponse(
        sku=result.sku, stockout_risk=result.stockout_risk,
        high_risk=result.high_risk, days_to_stockout=result.days_to_stockout,
        recommendation=result.recommendation,
    )


@router.post("/predict/stockouts", response_model=dict)
async def predict_stockouts_batch(
    body: BatchSKURequest,
    _auth: dict = Depends(require_auth),
):
    svc = _get_inference()
    results = svc.predict_stockouts(body.skus)
    return {
        sku: {
            "stockout_risk": r.stockout_risk,
            "high_risk": r.high_risk,
            "days_to_stockout": r.days_to_stockout,
            "recommendation": r.recommendation,
        }
        for sku, r in results.items()
    }


@router.post("/predict/all", response_model=list)
async def predict_all_insights(
    body: BatchSKURequest,
    _auth: dict = Depends(require_auth),
):
    """Полные insights (аномалии + stockout) для списка SKU."""
    svc = _get_inference()
    results = svc.predict_all(body.skus)
    out = []
    for sku, insights in results.items():
        item = {"sku": sku, "computed_at": insights.computed_at}
        if insights.anomaly:
            item["anomaly"] = {
                "is_anomaly": insights.anomaly.is_anomaly,
                "anomaly_score": insights.anomaly.anomaly_score,
                "confidence": insights.anomaly.confidence,
                "explanation": insights.anomaly.explanation,
            }
        if insights.stockout:
            item["stockout"] = {
                "stockout_risk": insights.stockout.stockout_risk,
                "high_risk": insights.stockout.high_risk,
                "days_to_stockout": insights.stockout.days_to_stockout,
                "recommendation": insights.stockout.recommendation,
            }
        out.append(item)
    return out


@router.get("/models", response_model=list[str])
async def list_models(_auth: dict = Depends(require_auth)):
    from ml.model_registry import ModelRegistry
    registry = ModelRegistry()
    return registry.list_models()


@router.get("/models/{model_name}", response_model=list[ModelVersionResponse])
async def get_model_versions(
    model_name: str,
    _auth: dict = Depends(require_auth),
):
    from ml.model_registry import ModelRegistry
    registry = ModelRegistry()
    versions = registry.list_versions(model_name)
    if not versions:
        raise HTTPException(404, f"Model '{model_name}' not found")
    return [
        ModelVersionResponse(
            model_name=v.model_name, version=v.version, status=v.status,
            metrics=v.metrics, training_samples=v.training_samples,
            trained_at=v.trained_at,
        )
        for v in versions
    ]


@router.post("/models/{model_name}/rollback")
async def rollback_model(
    model_name: str,
    version: str,
    _auth: dict = Depends(require_auth),
):
    from ml.model_registry import ModelRegistry
    registry = ModelRegistry()
    ok = registry.rollback(model_name, version)
    if not ok:
        raise HTTPException(400, f"Cannot rollback to version '{version}'")
    global _inference_svc
    if _inference_svc:
        _inference_svc.invalidate_cache()
    return {"status": "ok", "model_name": model_name, "rolled_back_to": version}


@router.post("/train")
async def trigger_training(
    body: TrainRequest,
    _auth: dict = Depends(require_auth),
):
    """Запускает training pipeline синхронно (для малых данных)."""
    from ml.training_pipeline import TrainingOrchestrator
    orch = TrainingOrchestrator()
    results = orch.run_all()
    global _inference_svc
    if _inference_svc:
        _inference_svc.invalidate_cache()
    return {
        "trained": [
            {
                "model": r.model_name, "version": r.version,
                "ok": r.ok, "metrics": r.metrics, "error": r.error,
            }
            for r in results
        ]
    }


@router.get("/drift/{model_name}", response_model=DriftReportResponse)
async def get_drift_report(
    model_name: str,
    _auth: dict = Depends(require_auth),
):
    from ml.drift_detector import DriftDetector
    detector = DriftDetector()
    report = detector.get_latest_report(model_name)
    if not report:
        raise HTTPException(404, f"No drift report found for '{model_name}'")
    n_drifted = sum(1 for fd in report.feature_drifts if fd.drift_level != "stable")
    return DriftReportResponse(
        model_name=report.model_name, version=report.version,
        overall_severity=report.overall_severity,
        data_drift_detected=report.data_drift_detected,
        concept_drift_detected=report.concept_drift_detected,
        n_drifted_features=n_drifted,
        recommendations=report.recommendations,
        report_date=report.report_date,
    )


@router.get("/features/stats")
async def get_feature_stats(_auth: dict = Depends(require_auth)):
    from feature_store.feature_pipeline import FeaturePipeline
    fp = FeaturePipeline()
    return fp.stats()
