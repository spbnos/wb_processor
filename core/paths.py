"""Единые пути проекта (корень, wb_platform, data/)."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WB_PLATFORM_DIR = PROJECT_ROOT / "wb_platform"
DATA_DIR = PROJECT_ROOT / "data"


def ensure_wb_platform_on_path() -> Path:
    """Добавляет wb_platform в sys.path для smart_mapping."""
    import sys

    if WB_PLATFORM_DIR.is_dir() and str(WB_PLATFORM_DIR) not in sys.path:
        sys.path.insert(0, str(WB_PLATFORM_DIR))
    return WB_PLATFORM_DIR
