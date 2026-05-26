"""
core/metrics.py — Prometheus метрики для всей платформы.

Метрики:
  COUNTERS:
    wb_files_processed_total{status, category}
    wb_tasks_total{type, status}
    wb_api_requests_total{method, path, status_code}
    wb_smart_mapping_decisions_total{level}    — AUTO/REVIEW/LOW/NO_MATCH

  HISTOGRAMS:
    wb_file_processing_duration_seconds{category}
    wb_api_request_duration_seconds{method, path}
    wb_ml_inference_duration_seconds{model}
    wb_feature_computation_duration_seconds

  GAUGES:
    wb_queue_depth{queue}           — Redis queue depth
    wb_review_queue_pending          — items waiting review
    wb_model_anomaly_rate{model}     — текущий anomaly rate
    wb_active_mappings_total         — кол-во активных маппингов

Использование:
    from core.metrics import (
        inc_files_processed, observe_file_duration,
        inc_api_request, observe_api_duration,
    )
"""
from __future__ import annotations

import time
import functools
from contextlib import contextmanager
from typing import Callable

from prometheus_client import (
    Counter, Histogram, Gauge, Summary,
    CollectorRegistry, REGISTRY,
    generate_latest, CONTENT_TYPE_LATEST,
)

# ─── Registry ────────────────────────────────────────────────────────
# Используем глобальный REGISTRY (prometheus default)
# В тестах можно передать изолированный registry

_BUCKETS_FAST   = (.005, .01, .025, .05, .1, .25, .5, 1, 2.5)
_BUCKETS_SLOW   = (.1, .25, .5, 1, 2.5, 5, 10, 30, 60)


# ─── Counters ────────────────────────────────────────────────────────

files_processed = Counter(
    "wb_files_processed_total",
    "Total files processed by pipeline",
    ["status", "category"],
)

tasks_total = Counter(
    "wb_tasks_total",
    "Total worker tasks processed",
    ["type", "status"],
)

api_requests = Counter(
    "wb_api_requests_total",
    "Total API requests",
    ["method", "path", "status_code"],
)

smart_mapping_decisions = Counter(
    "wb_smart_mapping_decisions_total",
    "Smart mapping decisions by confidence level",
    ["level"],        # auto_apply | needs_review | low_conf | no_match
)

review_queue_actions = Counter(
    "wb_review_queue_actions_total",
    "Review queue actions",
    ["action"],       # enqueue | approve | reject | expire
)


# ─── Histograms ──────────────────────────────────────────────────────

file_duration = Histogram(
    "wb_file_processing_duration_seconds",
    "File processing duration",
    ["category"],
    buckets=_BUCKETS_SLOW,
)

api_duration = Histogram(
    "wb_api_request_duration_seconds",
    "API request duration",
    ["method", "path"],
    buckets=_BUCKETS_FAST,
)

ml_inference_duration = Histogram(
    "wb_ml_inference_duration_seconds",
    "ML inference duration",
    ["model"],
    buckets=_BUCKETS_FAST,
)

feature_computation_duration = Histogram(
    "wb_feature_computation_duration_seconds",
    "Feature computation duration",
    buckets=_BUCKETS_SLOW,
)

smart_mapping_confidence = Histogram(
    "wb_smart_mapping_confidence",
    "Distribution of smart mapping confidence scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0],
)


# ─── Gauges ──────────────────────────────────────────────────────────

queue_depth = Gauge(
    "wb_queue_depth",
    "Current queue depth",
    ["queue"],        # high | normal | low | dead | review
)

active_mappings = Gauge(
    "wb_active_mappings_total",
    "Number of active mappings in registry",
)

model_anomaly_rate = Gauge(
    "wb_model_anomaly_rate",
    "Current anomaly rate reported by ML model",
    ["model"],
)

review_pending = Gauge(
    "wb_review_queue_pending",
    "Number of items pending review",
)


# ─── Helper functions ─────────────────────────────────────────────────

def inc_files_processed(status: str, category: str = "unknown") -> None:
    files_processed.labels(status=status, category=category).inc()


def inc_tasks(task_type: str, status: str) -> None:
    tasks_total.labels(type=task_type, status=status).inc()


def inc_api_request(method: str, path: str, status_code: int) -> None:
    api_requests.labels(
        method=method,
        path=_normalize_path(path),
        status_code=str(status_code),
    ).inc()


def observe_file_duration(seconds: float, category: str = "unknown") -> None:
    file_duration.labels(category=category).observe(seconds)


def observe_api_duration(seconds: float, method: str, path: str) -> None:
    api_duration.labels(
        method=method,
        path=_normalize_path(path),
    ).observe(seconds)


def observe_ml_inference(seconds: float, model: str) -> None:
    ml_inference_duration.labels(model=model).observe(seconds)


def inc_mapping_decision(level: str, confidence: float) -> None:
    smart_mapping_decisions.labels(level=level).inc()
    smart_mapping_confidence.observe(confidence)


def set_queue_depth(queue_name: str, depth: int) -> None:
    queue_depth.labels(queue=queue_name).set(depth)


def set_review_pending(count: int) -> None:
    review_pending.set(count)


def set_active_mappings(count: int) -> None:
    active_mappings.set(count)


def set_anomaly_rate(model: str, rate: float) -> None:
    model_anomaly_rate.labels(model=model).set(rate)


# ─── Context manager: timed block ────────────────────────────────────

@contextmanager
def timed(histogram: Histogram, *label_values: str):
    """
    Context manager для измерения времени.

    with timed(file_duration, "wb_report"):
        process_file(...)
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        if label_values:
            histogram.labels(*label_values).observe(elapsed)
        else:
            histogram.observe(elapsed)


# ─── Decorator: @track_duration ──────────────────────────────────────

def track_duration(histogram: Histogram, *label_values: str):
    """
    Декоратор для автоматического трекинга времени.

    @track_duration(ml_inference_duration, "anomaly_detector")
    def predict(sku): ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with timed(histogram, *label_values):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# ─── Metrics export ──────────────────────────────────────────────────

def get_metrics_output() -> tuple[bytes, str]:
    """Возвращает (data, content_type) для /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def _normalize_path(path: str) -> str:
    """Нормализует path для label (убирает динамические части)."""
    import re
    path = re.sub(r"/[0-9a-f-]{8,}",   "/{id}",  path)
    path = re.sub(r"/\d+",              "/{id}",  path)
    return path
