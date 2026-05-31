"""
core/xlsx_utils.py — утилиты для чтения нестандартных xlsx файлов WB.

WB экспортирует xlsx с 'xl/SharedStrings.xml' (заглавная S) вместо стандартного
'xl/sharedStrings.xml'. На Windows это работает (NTFS case-insensitive), 
на Linux — нет. Исправляем при чтении.
"""
from __future__ import annotations
import io
import zipfile
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def read_excel_safe(filepath: Path, header: int = 0, nrows: int | None = None) -> Optional[pd.DataFrame]:
    """
    Читает xlsx/xls с автоматическим исправлением WB-специфичных проблем:
      1. SharedStrings.xml case-sensitivity bug
      2. Fallback через стандартный read_excel
    """
    kw: dict = {"header": header}
    if nrows is not None:
        kw["nrows"] = nrows

    ext = filepath.suffix.lower()

    if ext in (".xlsx",):
        # Try WB fix first
        fixed = _fix_shared_strings(filepath)
        if fixed is not None:
            try:
                return pd.read_excel(fixed, **kw)
            except Exception as e:
                logger.debug(f"[xlsx_utils] Fixed buf read failed: {e}")

        # Standard openpyxl
        try:
            return pd.read_excel(filepath, **kw)
        except Exception as e:
            logger.debug(f"[xlsx_utils] openpyxl failed: {e}")

    # xls or fallback
    try:
        return pd.read_excel(filepath, engine="xlrd", **kw)
    except Exception as e:
        logger.debug(f"[xlsx_utils] xlrd failed: {e}")

    return None


def _fix_shared_strings(filepath: Path) -> Optional[io.BytesIO]:
    """
    Если xlsx содержит 'xl/SharedStrings.xml' вместо 'xl/sharedStrings.xml',
    возвращает исправленный io.BytesIO; иначе None (исправление не нужно).
    """
    try:
        with open(filepath, "rb") as f:
            raw = f.read()
        with zipfile.ZipFile(io.BytesIO(raw)) as zin:
            names = zin.namelist()
            # Already correct or no SharedStrings at all
            if "xl/SharedStrings.xml" not in names:
                return None
            if "xl/sharedStrings.xml" in names:
                return None  # Both exist — no fix needed

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    content = zin.read(item.filename)
                    # Patch references in XML files
                    if item.filename in ("xl/workbook.xml", "[Content_Types].xml",
                                         "xl/_rels/workbook.xml.rels"):
                        content = content.replace(
                            b"SharedStrings.xml", b"sharedStrings.xml"
                        )
                    # Rename the entry itself
                    item.filename = item.filename.replace(
                        "xl/SharedStrings.xml", "xl/sharedStrings.xml"
                    )
                    zout.writestr(item, content)
            buf.seek(0)
            logger.debug(f"[xlsx_utils] Fixed SharedStrings.xml case for {filepath.name}")
            return buf
    except Exception as e:
        logger.debug(f"[xlsx_utils] _fix_shared_strings error: {e}")
        return None
