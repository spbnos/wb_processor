import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Paths
DATA_DIR = BASE_DIR / "data"
INCOMING_DIR = BASE_DIR / "incoming"
PROCESSED_DIR = BASE_DIR / "processed"
FAILED_DIR = BASE_DIR / "failed"
DEFERRED_DIR = BASE_DIR / "deferred"  # низкая уверенность маппинга (опционально)

# Create dirs if not exist
for d in [DATA_DIR, INCOMING_DIR, PROCESSED_DIR, FAILED_DIR, DEFERRED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Database
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "wb_processor")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")

# WB API (https://dev.wildberries.ru) — ключ категории "Продвижение" для аудита РК.
# Не обязателен для работы остальной системы; модуль promotion_audit вернёт
# понятную ошибку 503, если ключ не задан.
WB_API_KEY = os.getenv("WB_API_KEY", "")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# File processing
SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
SAMPLE_ROWS = 5  # rows to read for format detection

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = BASE_DIR / "logs" / "processor.log"
LOG_FILE.parent.mkdir(exist_ok=True)
