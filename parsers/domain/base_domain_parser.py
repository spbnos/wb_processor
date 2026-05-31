"""base_domain_parser.py — базовый класс для всех domain парсеров."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import pandas as pd
import logging
logger = logging.getLogger(__name__)


@dataclass
class DomainParseResult:
    report_id:   str
    filepath:    Path
    domain:      str
    db_table:    str
    df:          pd.DataFrame
    rows:        int
    errors:      list[str] = field(default_factory=list)
    warnings:    list[str] = field(default_factory=list)
    ok:          bool = True
    period_from: Optional[str] = None
    period_to:   Optional[str] = None
    metadata:    dict = field(default_factory=dict)


class BaseDomainParser:
    report_id:   str = "base"
    domain:      str = "unknown"
    db_table:    str = "unknown"
    header_row:  int = 0

    def parse(self, filepath: Path, header_row: int = 0) -> DomainParseResult:
        raise NotImplementedError

    def _read(self, filepath: Path, header_row: int) -> Optional[pd.DataFrame]:
        """Read xlsx/csv with WB-specific bug fixes via xlsx_utils."""
        ext = filepath.suffix.lower()
        try:
            if ext in (".xlsx", ".xls"):
                # Use xlsx_utils for WB SharedStrings.xml case bug
                try:
                    from core.xlsx_utils import read_excel_safe
                    result = read_excel_safe(filepath, header=header_row)
                    if result is not None:
                        return result
                except ImportError:
                    pass
                # Fallback: standard engines
                for engine in [None, "xlrd"]:
                    try:
                        kw = {"engine": engine} if engine else {}
                        return pd.read_excel(filepath, header=header_row, **kw)
                    except Exception:
                        continue
            elif ext == ".csv":
                try:
                    import chardet
                    enc = chardet.detect(open(filepath,"rb").read(32768)).get("encoding","utf-8")
                except ImportError:
                    enc = "utf-8"
                return pd.read_csv(filepath, header=header_row, encoding=enc)
        except Exception as e:
            logger.error(f"[{self.report_id}] read error {filepath.name}: {e}")
        return None

    @staticmethod
    def _f(v) -> Optional[float]:
        if v is None: return None
        try:
            if pd.isna(v): return None
            return float(v)
        except: return None

    @staticmethod
    def _s(v) -> str:
        if v is None: return ""
        try:
            if str(v) in ("nan","None","NaT",""): return ""
            return str(v).strip()
        except: return ""
