"""ad_cost_parser.py — История затрат (реклама)."""
from __future__ import annotations
from pathlib import Path
import re, pandas as pd, logging
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult
logger = logging.getLogger(__name__)
_MAP={"ID кампании":"campaign_id","Кампания":"campaign_name","Раздел":"section",
      "Дата списания":"charge_date","Источник списания":"charge_source","Сумма":"amount","Номер документа":"doc_number"}

class AdCostParser(BaseDomainParser):
    report_id="ad_cost_history"; domain="advertising_intelligence"; db_table="ad_costs"
    def parse(self, filepath, header_row=0):
        df=self._read(filepath,header_row)
        if df is None:
            return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
                db_table=self.db_table,df=pd.DataFrame(),rows=0,ok=False,errors=[f"Cannot read {filepath.name}"])
        df=df.rename(columns={k:v for k,v in _MAP.items() if k in df.columns})
        if "amount" in df.columns: df["amount"]=pd.to_numeric(df["amount"],errors="coerce").fillna(0.0)
        if "charge_date" in df.columns: df["charge_date"]=pd.to_datetime(df["charge_date"],errors="coerce")
        pf=pt=None
        m=re.search(r"(\d{4}-\d{2}-\d{2})",filepath.name)
        if m: pf=pt=m.group(1)
        if "charge_date" in df.columns and not df["charge_date"].dropna().empty:
            pf=str(df["charge_date"].dropna().min().date()); pt=str(df["charge_date"].dropna().max().date())
        df["report_type"]=self.report_id
        logger.info(f"[ad_cost] Parsed {len(df)} rows from {filepath.name}")
        return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
            db_table=self.db_table,df=df,rows=len(df),ok=True,period_from=pf,period_to=pt)
