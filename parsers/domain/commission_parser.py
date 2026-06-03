"""
commission_parser.py — Таблица комиссий WB по предметам.

Файл: commission.xlsx
Содержит базовые ставки ВВ% для 7413 предметов по 6 схемам работы:
  - FBO (Склад WB, %)
  - FBS-WB (везу на склад WB, %)
  - FBS-DBS (везу самостоятельно до клиента, %)
  - FBS-Express (экспресс, %)
  - FBS-Pickup (самовывоз, %)
  - Бронирование (%)

Загружается в: data/wb_commissions.json (отдельно от loaded/, т.к. это справочник)
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import logging
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult

logger = logging.getLogger(__name__)

_COL_MAP = {
    "Категория":                                                         "category",
    "Предмет":                                                           "subject",
    "Склад WB, %":                                                       "fbo_pct",
    "Склад продавца - везу на склад WB, %":                             "fbs_wb_pct",
    "Склад продавца - везу самостоятельно до клиента, %":               "fbs_dbs_pct",
    "Склад продавца - везу самостоятельно до клиента экспресс, %":      "fbs_express_pct",
    "Склад продавца - самовывоз":                                        "fbs_pickup_pct",
    "Бронирование":                                                      "booking_pct",
}


class CommissionParser(BaseDomainParser):
    report_id  = "wb_commission_table"
    domain     = "reference_intelligence"
    db_table   = "wb_commissions"
    header_row = 0

    def parse(self, filepath: Path, header_row: int = 0) -> DomainParseResult:
        df = self._read(filepath, header_row)
        if df is None:
            return DomainParseResult(
                report_id=self.report_id, filepath=filepath,
                domain=self.domain, db_table=self.db_table,
                df=pd.DataFrame(), rows=0, ok=False,
                errors=[f"Cannot read {filepath.name}"],
            )

        df = df.rename(columns={k: v for k, v in _COL_MAP.items() if k in df.columns})

        # Normalize percentage values: "29,50" → 29.5
        for pct_col in ["fbo_pct","fbs_wb_pct","fbs_dbs_pct","fbs_express_pct","fbs_pickup_pct","booking_pct"]:
            if pct_col in df.columns:
                df[pct_col] = df[pct_col].astype(str).str.replace(",",".").str.strip()
                df[pct_col] = pd.to_numeric(df[pct_col], errors="coerce")

        # Drop empty rows
        df = df.dropna(subset=["subject"]).copy()
        df["subject"]  = df["subject"].astype(str).str.strip()
        df["category"] = df.get("category", pd.Series([""] * len(df))).astype(str).str.strip()
        df["report_type"] = self.report_id

        logger.info(f"[commission] Parsed {len(df)} subjects from {filepath.name}")
        return DomainParseResult(
            report_id=self.report_id, filepath=filepath,
            domain=self.domain, db_table=self.db_table,
            df=df, rows=len(df), ok=True,
            metadata={"unique_categories": df["category"].nunique()},
        )
