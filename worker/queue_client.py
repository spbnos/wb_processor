"""
worker/queue_client.py — минимальная восстановленная заглушка.

Пакет worker/ отсутствовал в git-истории (не закоммичен ранее). Этот файл
восстанавливает mock-режим, явно подразумеваемый существующим кодом
(api/deps.py: `RedisQueueClient(mock=True)  # mock до Docker`).

mock=True  → задачи хранятся в памяти процесса (без реального Redis),
             поведение синхронное: enqueue сразу выполняет задачу через
             smart_pipeline, если это PROCESS_FILE — иначе просто хранит её
             в статусе queued. Это НЕ новая бизнес-логика, а минимальная
             реализация, нужная только чтобы существующие FastAPI-роуты
             (files.py: upload/tasks/queue) физически работали без падения
             сервера при импорте.

mock=False → не реализовано (требует реального Redis + Docker, см. комментарий
             "mock до Docker" в api/deps.py — это будущая, не текущая задача).
"""
from __future__ import annotations

import logging
from typing import Optional

from worker.task_models import Task

logger = logging.getLogger(__name__)


class RedisQueueClient:
    def __init__(self, mock: bool = True):
        self.mock = mock
        self._tasks: dict[str, Task] = {}
        if not mock:
            raise NotImplementedError(
                "RedisQueueClient(mock=False) требует реальный Redis — "
                "не реализовано (см. комментарий 'mock до Docker' в api/deps.py). "
                "Используйте mock=True."
            )

    def enqueue(self, task: Task) -> str:
        """Кладёт задачу в очередь. В mock-режиме обрабатывает синхронно,
        если это PROCESS_FILE задача — через существующий smart_pipeline."""
        self._tasks[task.id] = task
        if task.type == "PROCESS_FILE":
            filepath = task.payload.get("filepath")
            try:
                from smart_pipeline import SmartPipeline
                from pathlib import Path as _P

                pipeline = SmartPipeline()
                result_status = pipeline.process_file(_P(filepath))
                task.status = "done"
                task.result = {"pipeline_status": result_status}
            except Exception as e:  # noqa: BLE001
                logger.error(f"[worker.mock] PROCESS_FILE task {task.id} failed: {e}")
                task.status = "error"
                task.error = str(e)
        else:
            task.status = "queued"
        return task.id

    def get_result(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def queue_lengths(self) -> dict:
        pending = sum(1 for t in self._tasks.values() if t.status == "queued")
        return {"high": 0, "normal": pending, "low": 0, "dead": 0}
