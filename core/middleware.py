"""
core/middleware.py — FastAPI middleware для observability.

Middleware:
  1. RequestTimingMiddleware  — X-Process-Time-Ms header + Prometheus metrics
  2. RequestLoggingMiddleware — structured log каждого запроса
  3. RequestIDMiddleware      — генерирует X-Request-ID и биндит в structlog ctx

Использование (в api/main.py):
    from core.middleware import add_observability_middleware
    add_observability_middleware(app)
"""
from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from core.logging import get_logger, bind_ctx, clear_ctx
from core.metrics import inc_api_request, observe_api_duration

log = get_logger("api.middleware")

_SKIP_PATHS = {"/metrics", "/api/stats/health", "/docs", "/openapi.json", "/redoc"}


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Генерирует X-Request-ID и привязывает к structlog контексту."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        bind_ctx(request_id=rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        clear_ctx()
        return response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Замеряет latency → header + Prometheus histogram."""

    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - t0
        ms = int(elapsed * 1000)

        response.headers["X-Process-Time-Ms"] = str(ms)

        if request.url.path not in _SKIP_PATHS:
            observe_api_duration(elapsed, request.method, request.url.path)
            inc_api_request(request.method, request.url.path, response.status_code)

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Логирует каждый запрос в JSON формате."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        status = response.status_code
        level = "warning" if status >= 400 else "info"

        getattr(log, level)(
            "http.request",
            method=request.method,
            path=request.url.path,
            status_code=status,
            duration_ms=elapsed_ms,
            client=request.client.host if request.client else "unknown",
        )
        return response


def add_observability_middleware(app: ASGIApp) -> None:
    """Добавляет все observability middleware к FastAPI приложению."""
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestTimingMiddleware)
    app.add_middleware(RequestIDMiddleware)
