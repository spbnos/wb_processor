"""
worker/task_models.py — минимальная восстановленная заглушка.

Пакет worker/ отсутствовал в git-истории репозитория (не закоммичен ранее),
хотя api/deps.py и api/routes/files.py явно рассчитаны на mock-режим
(`RedisQueueClient(mock=True)  # mock до Docker` — комментарий из
api/deps.py). Этот файл восстанавливает только то поведение, которое уже
подразумевалось существующим кодом, не добавляя новой логики/расчётов.

Контракт (выведен из фактического использования в api/routes/files.py):
  make_process_file_task(path, priority) -> Task
  Task.id / Task.status / Task.result / Task.error
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Task:
    id: str
    type: str
    payload: dict
    priority: int = 5
    status: str = "queued"          # queued | running | done | error
    result: Optional[dict] = None
    error: Optional[str] = None


def make_process_file_task(filepath: str, priority: int = 5) -> Task:
    """Задача обработки файла, кладётся в очередь через RedisQueueClient.enqueue()."""
    return Task(
        id=str(uuid.uuid4()),
        type="PROCESS_FILE",
        payload={"filepath": filepath},
        priority=priority,
    )
