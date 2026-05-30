"""
api/main.py — FastAPI application.

Запуск:
    uvicorn api.main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs
ReDoc:      http://localhost:8000/redoc
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import time

from api.routes import files, mappings, review, stats, ml, kb
from core.middleware import add_observability_middleware
from core.metrics import get_metrics_output
from starlette.responses import Response as StarletteResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="WB Intelligent Data Platform",
    description=(
        "Self-learning ML-driven platform для обработки файлов Wildberries. "
        "Zero manual input — SmartMapper автоматически определяет формат файлов."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS — для React Dashboard ─────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request timing middleware ──────────────────────────────
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    import uuid
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed:.1f}"
    response.headers["X-Request-ID"] = rid
    return response

# ── Global exception handler ──────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )

# ── Routers ───────────────────────────────────────────────
@app.get("/metrics", include_in_schema=False)
async def metrics():
    data, content_type = get_metrics_output()
    return StarletteResponse(content=data, media_type=content_type)


app.include_router(files.router,    prefix="/api")
app.include_router(mappings.router, prefix="/api")
app.include_router(review.router,   prefix="/api")
app.include_router(stats.router,    prefix="/api")
app.include_router(ml.router,      prefix="/api")
app.include_router(kb.router,      prefix="/api")

# Analytics routes (domain data - sales, finance, stocks, ads, returns, supply)
try:
    from api.routes import analytics as analytics_module
    app.include_router(analytics_module.router, prefix="/api")
    logger.info("[main] Analytics router registered")
except ImportError as _e:
    logger.warning(f"[main] Analytics router not available: {_e}")

@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": "WB Intelligent Data Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/stats/health",
    }
