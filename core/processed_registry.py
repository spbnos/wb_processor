"""
Реестр обработанных файлов (локальный режим, без БД).

Ключ: SHA256 содержимого. Защита от повторной загрузки при scan/retry.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.paths import DATA_DIR

logger = logging.getLogger(__name__)

_DEFAULT_PATH = DATA_DIR / "processed_registry.json"


@dataclass
class ProcessedRecord:
    file_hash: str
    filename: str
    status: str  # ok | error | skipped
    processed_at: str
    row_count: int = 0
    error: str = ""


class ProcessedFileRegistry:
    def __init__(self, path: Path = _DEFAULT_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def is_processed(self, file_hash: str) -> bool:
        rec = self._data().get(file_hash)
        return rec is not None and rec.get("status") == "ok"

    def get(self, file_hash: str) -> Optional[dict]:
        return self._data().get(file_hash)

    def register(
        self,
        file_hash: str,
        filename: str,
        status: str = "ok",
        row_count: int = 0,
        error: str = "",
    ) -> None:
        data = self._data()
        data[file_hash] = {
            "file_hash": file_hash,
            "filename": filename,
            "status": status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "row_count": row_count,
            "error": error or None,
        }
        self._write(data)
        logger.debug(f"[registry] {status}: {filename} ({file_hash[:12]}…)")

    def stats(self) -> dict:
        data = self._data()
        by_status: dict[str, int] = {}
        for rec in data.values():
            s = rec.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
        return {"total": len(data), "by_status": by_status}

    def _data(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict) -> None:
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
