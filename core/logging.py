"""
core/logging.py — Structured logging для всей платформы.

Возможности:
  - JSON формат в prod, human-readable в dev
  - request_id / task_id / file_id через contextvars
  - автоматический timing для функций (@timed_log)
  - уровни: DEBUG / INFO / WARNING / ERROR / CRITICAL
  - интеграция с FastAPI middleware

Использование:
    from core.logging import get_logger, bind_ctx
    log = get_logger(__name__)
    bind_ctx(request_id="abc123", user="api")
    log.info("file.processed", file="wb_sales.csv", rows=1500)
"""
from __future__ import annotations

import functools
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Callable

import structlog

# ─── Context variables (thread-safe per-request state) ──────────────
_request_id: ContextVar[str] = ContextVar("request_id", default="")
_task_id:    ContextVar[str] = ContextVar("task_id",    default="")
_file_name:  ContextVar[str] = ContextVar("file_name",  default="")
_user:       ContextVar[str] = ContextVar("user",       default="system")

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_ENV       = os.getenv("ENV", "development")
_JSON_LOGS = os.getenv("JSON_LOGS", "false").lower() == "true" or _ENV == "production"


def _add_context(logger, method, event_dict: dict) -> dict:
    """Structlog processor: добавляет контекстные переменные."""
    if rid := _request_id.get():
        event_dict["request_id"] = rid
    if tid := _task_id.get():
        event_dict["task_id"] = tid
    if fn := _file_name.get():
        event_dict["file"] = fn
    if u := _user.get():
        event_dict["user"] = u
    return event_dict


def _add_timestamp(logger, method, event_dict: dict) -> dict:
    event_dict["timestamp"] = structlog.processors.TimeStamper(fmt="iso")(
        logger, method, {"timestamp": ""}
    )["timestamp"]
    return event_dict


def configure_logging():
    """Настраивает structlog + stdlib logging. Вызвать один раз при старте."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        _add_context,
    ]

    if _JSON_LOGS:
        # Production: JSON формат
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: human-readable с цветами
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=shared_processors + [
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, _LOG_LEVEL, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Настраиваем stdlib чтобы не дублировал вывод
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, _LOG_LEVEL, logging.INFO),
    )
    # Заглушаем шумные библиотеки
    for noisy in ("watchdog", "sqlalchemy.engine", "urllib3", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """Возвращает настроенный logger для модуля."""
    return structlog.get_logger(name)


def bind_ctx(**kwargs: str) -> None:
    """Привязывает значения к текущему контексту (все последующие логи добавят их)."""
    if "request_id" in kwargs:
        _request_id.set(kwargs["request_id"])
    if "task_id" in kwargs:
        _task_id.set(kwargs["task_id"])
    if "file_name" in kwargs:
        _file_name.set(kwargs["file_name"])
    if "user" in kwargs:
        _user.set(kwargs["user"])


def clear_ctx() -> None:
    """Сбрасывает контекст (вызывать в конце request/task)."""
    _request_id.set("")
    _task_id.set("")
    _file_name.set("")
    _user.set("system")


def new_request_id() -> str:
    rid = str(uuid.uuid4())[:8]
    _request_id.set(rid)
    return rid


# ─── Decorator: @timed_log ────────────────────────────────────────────
def timed_log(operation: str = "", log_args: bool = False):
    """
    Декоратор: логирует вызов функции + время выполнения.

    @timed_log("file.parse")
    def parse_file(path): ...
    → INFO  file.parse  duration_ms=142  args.path="wb.csv"
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            log = get_logger(__name__)
            op  = operation or func.__qualname__
            extra: dict[str, Any] = {}
            if log_args and kwargs:
                extra.update({f"arg.{k}": str(v)[:80] for k, v in kwargs.items()})
            t0 = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                ms = int((time.perf_counter() - t0) * 1000)
                log.info(op, duration_ms=ms, status="ok", **extra)
                return result
            except Exception as exc:
                ms = int((time.perf_counter() - t0) * 1000)
                log.error(op, duration_ms=ms, status="error",
                          error=str(exc), **extra)
                raise
        return wrapper
    return decorator


# Вызываем configure при импорте
configure_logging()
