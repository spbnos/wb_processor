"""paid_storage_parser.py — Платное хранение."""
from __future__ import annotations
from pathlib import Path
import re, pandas as pd, logging
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult
logger = logging.getLogger(__name__)

class PaidStorageParser(BaseDomainParser):
    report_id="paid_storage"; domain="finance_intelligence"; db_table="paid_storage"
    def parse(self, filepath, header_row=0):
        df=self._read(filepath,header_row)
        if df is None:
            return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
                db_table=self.db_table,df=pd.DataFrame(),rows=0,ok=False,errors=[f"Cannot read {filepath.name}"])
        pf=pt=None
        if not df.empty and df.shape[1]>1:
            first=str(df.iloc[0,1]) if df.shape[1]>1 else ""
            dates=re.findall(r"(\d{4}-\d{2}-\d{2})",first)
            if len(dates)>=2: pf,pt=dates[0],dates[1]
            elif len(dates)==1: pf=pt=dates[0]
        if df.shape[1]==2: df.columns=["field","value"]
        df["report_type"]=self.report_id; df["source_file"]=filepath.name
        logger.info(f"[paid_storage] Parsed {len(df)} rows from {filepath.name}")
        return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
            db_table=self.db_table,df=df,rows=len(df),ok=True,period_from=pf,period_to=pt)
