"""returns_parser.py — Возвраты (merged header: row 1 = actual cols)."""
from __future__ import annotations
from pathlib import Path
import pandas as pd, logging
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult
logger = logging.getLogger(__name__)
_MAP={"Бренд":"brand","Предмет":"category","Баркод":"barcode","Артикул WB":"sku_id",
      "Статус":"status","Готов к выдаче":"ready_date","Забрали":"picked_date",
      "Истёк срок хранения":"expired_date","Тип":"return_type","Дата заказа":"order_date",
      "Причина":"return_reason","Номер сборочного задания":"assembly_task_id","Srid":"srid",
      "Адрес":"pvz_address","ID":"pvz_id","КИЗ":"kiz","Стикер":"sticker"}

class ReturnsParser(BaseDomainParser):
    report_id="returns"; domain="returns_intelligence"; db_table="returns"; header_row=1
    def parse(self, filepath, header_row=1):
        df=self._read(filepath,header_row)
        if df is None:
            return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
                db_table=self.db_table,df=pd.DataFrame(),rows=0,ok=False,errors=[f"Cannot read {filepath.name}"])
        df=df.loc[:,~df.columns.str.startswith("Unnamed")]
        df=df.rename(columns={k:v for k,v in _MAP.items() if k in df.columns})
        for c in ["ready_date","picked_date","expired_date","order_date"]:
            if c in df.columns: df[c]=pd.to_datetime(df[c],errors="coerce")
        pf=pt=None
        if "order_date" in df.columns and not df["order_date"].dropna().empty:
            pf=str(df["order_date"].dropna().min().date()); pt=str(df["order_date"].dropna().max().date())
        df["report_type"]=self.report_id
        logger.info(f"[returns] Parsed {len(df)} rows from {filepath.name}")
        return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
            db_table=self.db_table,df=df,rows=len(df),ok=True,period_from=pf,period_to=pt)
