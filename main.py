#!/usr/bin/env python3
"""
WB File Processor — точка входа.

Использование:
    # Запустить watcher (следить за incoming/)
    python main.py run

    # Обработать существующие файлы один раз
    python main.py scan

    # Управление маппингами
    python main.py mappings list
    python main.py mappings show 1
    python main.py mappings edit 1
    python main.py mappings delete 1
    python main.py mappings export
    python main.py mappings import backup.json

    # Статус
    python main.py status

    # С PostgreSQL
    python main.py run --db

Рекомендуется Python 3.12:
    py -3.12 -m pip install -r requirements.txt
    py -3.12 main.py scan
"""
import sys
import logging
from pathlib import Path

# Добавляем корень проекта и wb_platform в PATH
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "wb_platform"))

from config.settings import LOG_LEVEL, LOG_FILE


def _setup_logging():
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )
    # Уменьшаем шум от watchdog и SQLAlchemy
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


_setup_logging()

from cli.commands import cli

if __name__ == "__main__":
    cli()
