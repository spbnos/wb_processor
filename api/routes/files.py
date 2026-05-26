"""
routes/files.py — файлы и задачи обработки.

POST /files/upload      — загрузить файл → enqueue
GET  /files/tasks/{id}  — статус задачи
GET  /files/queue       — состояние очереди
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from api.auth import require_auth
from api.deps import get_redis_client, get_storage
from worker.queue_client import RedisQueueClient
from worker.task_models import make_process_file_task

router = APIRouter(prefix="/files", tags=["files"])


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None


class QueueStatusResponse(BaseModel):
    high: int
    normal: int
    low: int
    dead: int


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    file: UploadFile = File(...),
    _auth: dict = Depends(require_auth),
    redis: RedisQueueClient = Depends(get_redis_client),
):
    """
    Принимает файл (.xlsx/.csv), сохраняет во временную папку,
    создаёт задачу PROCESS_FILE и кладёт в Redis очередь.

    Returns: { task_id, filename, status }
    """
    suffix = Path(file.filename or "upload").suffix.lower()
    allowed = {".xlsx", ".xls", ".csv"}
    if suffix not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Allowed: {allowed}",
        )

    # Сохраняем во incoming/
    from config.settings import INCOMING_DIR
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    dest = INCOMING_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    task = make_process_file_task(str(dest), priority=5)
    task_id = redis.enqueue(task)

    return {
        "task_id": task_id,
        "filename": file.filename,
        "status": "queued",
        "message": "File uploaded and queued for processing",
    }


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    _auth: dict = Depends(require_auth),
    redis: RedisQueueClient = Depends(get_redis_client),
):
    """Возвращает статус и результат задачи по ID."""
    task = redis.get_result(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id!r} not found (may still be pending)",
        )
    return TaskStatusResponse(
        task_id=task.id,
        status=task.status,
        result=task.result,
        error=task.error,
    )


@router.get("/queue", response_model=QueueStatusResponse)
async def get_queue_status(
    _auth: dict = Depends(require_auth),
    redis: RedisQueueClient = Depends(get_redis_client),
):
    """Состояние очередей Redis."""
    lengths = redis.queue_lengths()
    return QueueStatusResponse(
        high=lengths.get("high", 0),
        normal=lengths.get("normal", 0),
        low=lengths.get("low", 0),
        dead=lengths.get("dead", 0),
    )
