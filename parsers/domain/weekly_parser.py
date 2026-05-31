"""weekly_parser.py — Еженедельный отчёт (финансовый сводный)."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import logging
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult
logger = logging.getLogger(__name__)

_MAP = {
    "№ отчета":"report_number","Юридическое лицо":"legal_entity",
    "Дата начала":"period_start","Дата конца":"period_end","Дата формирования":"formed_at",
    "Тип отчета":"report_type_wb","Продажа":"sales_amount",
    "К перечислению за товар":"seller_payment","Согласованная скидка, %":"agreed_discount_pct",
    "Стоимость логистики":"logistics_cost","Стоимость хранения":"storage_cost",
    "Стоимость операций на приемке":"acceptance_cost","Прочие удержания/выплаты":"other_deductions",
    "Общая сумма штрафов":"total_penalties",
    "Корректировка Вознаграждения Вайлдберриз (ВВ)":"vv_adjustment",
    "Стоимость участия в программе лояльности":"loyalty_cost","Итого к оплате":"total_payable",
    "Валюта":"currency",
}

class WeeklyReportParser(BaseDomainParser):
    report_id="weekly_report"; domain="finance_intelligence"; db_table="weekly_reports"

    def parse(self, filepath: Path, header_row: int = 0) -> DomainParseResult:
        df = self._read(filepath, header_row)
        if df is None:
            return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
                db_table=self.db_table,df=pd.DataFrame(),rows=0,ok=False,errors=[f"Cannot read {filepath.name}"])
        df = df.rename(columns={k:v for k,v in _MAP.items() if k in df.columns})
        for c in ["sales_amount","seller_payment","logistics_cost","storage_cost",
                  "acceptance_cost","other_deductions","total_penalties","total_payable","loyalty_cost"]:
            if c in df.columns: df[c]=pd.to_numeric(df[c],errors="coerce").fillna(0.0)
        for c in ["period_start","period_end","formed_at"]:
            if c in df.columns:
                try:
                    df[c]=pd.to_datetime(df[c],errors="coerce",utc=True).dt.tz_localize(None)
                except Exception:
                    df[c]=pd.to_datetime(df[c],errors="coerce")
        pf=pt=None
        if "period_start" in df.columns and not df["period_start"].dropna().empty:
            pf=str(df["period_start"].dropna().min().date())
        if "period_end" in df.columns and not df["period_end"].dropna().empty:
            pt=str(df["period_end"].dropna().max().date())
        df["report_type"]=self.report_id
        logger.info(f"[weekly] Parsed {len(df)} rows from {filepath.name}")
        return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
            db_table=self.db_table,df=df,rows=len(df),ok=True,period_from=pf,period_to=pt)
