"""stocks_parser.py — Остатки на складе (pivot warehouse cols → long format)."""
from __future__ import annotations
from pathlib import Path
import pandas as pd, logging
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult
logger = logging.getLogger(__name__)
_FIXED={"Бренд":"brand","Предмет":"category","Артикул продавца":"seller_article",
        "Артикул WB":"sku_id","Объем, л":"volume_l","Баркод":"barcode",
        "В пути до получателей":"in_transit_to_customer","В пути возвраты на склад WB":"in_transit_returns",
        "Всего находится на складах":"total_stock"}

class StocksParser(BaseDomainParser):
    report_id="warehouse_stocks"; domain="warehouse_intelligence"; db_table="warehouse_stocks"
    def parse(self, filepath, header_row=0):
        df=self._read(filepath,header_row)
        if df is None:
            return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
                db_table=self.db_table,df=pd.DataFrame(),rows=0,ok=False,errors=[f"Cannot read {filepath.name}"])
        df=df.rename(columns={k:v for k,v in _FIXED.items() if k in df.columns})
        fixed_set=set(_FIXED.values())&set(df.columns)
        wh_cols=[c for c in df.columns if c not in fixed_set and c not in ("report_type",)]
        _STR_COLS = {"brand","category","seller_article","sku_id","barcode"}
        for c in list(fixed_set)+wh_cols:
            if c in df.columns and c not in _STR_COLS:
                try: df[c]=pd.to_numeric(df[c],errors="coerce").fillna(0.0)
                except Exception: pass
        if wh_cols:
            id_cols=[c for c in fixed_set if c in df.columns]
            melted=df.melt(id_vars=id_cols,value_vars=wh_cols,var_name="warehouse_name",value_name="quantity")
            melted=melted[melted["quantity"]>0].copy()
            melted["report_type"]=self.report_id
            result_df=melted
        else:
            df["report_type"]=self.report_id; result_df=df
        logger.info(f"[stocks] Parsed {len(result_df)} rows (long) from {filepath.name}")
        return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
            db_table=self.db_table,df=result_df,rows=len(result_df),ok=True,
            metadata={"warehouse_cols":wh_cols})
