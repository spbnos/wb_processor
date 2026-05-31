"""price_template_parser.py — Шаблон обновления цен и скидок."""
from __future__ import annotations
from pathlib import Path
import pandas as pd, logging
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult
logger = logging.getLogger(__name__)
_MAP={"Бренд":"brand","Категория":"category","Артикул WB":"sku_id","Артикул продавца":"seller_article",
      "Последний баркод":"barcode","Остатки WB":"stock_wb","Остатки продавца":"stock_seller",
      "Оборачиваемость":"turnover_days","Текущая цена":"current_price","Новая цена, RUB":"new_price",
      "Текущая скидка":"current_discount_pct","Новая скидка":"new_discount_pct",
      "Цена со скидкой":"discounted_price","Наличие ошибки":"has_error"}

class PriceTemplateParser(BaseDomainParser):
    report_id="price_template"; domain="pricing_intelligence"; db_table="price_templates"
    def parse(self, filepath, header_row=0):
        df=self._read(filepath,header_row)
        if df is None:
            return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
                db_table=self.db_table,df=pd.DataFrame(),rows=0,ok=False,errors=[f"Cannot read {filepath.name}"])
        df=df.rename(columns={k:v for k,v in _MAP.items() if k in df.columns})
        for c in ["stock_wb","stock_seller","current_price","new_price","current_discount_pct","new_discount_pct","discounted_price","turnover_days"]:
            if c in df.columns: df[c]=pd.to_numeric(df[c],errors="coerce")
        df["report_type"]=self.report_id
        logger.info(f"[price_template] Parsed {len(df)} rows from {filepath.name}")
        return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
            db_table=self.db_table,df=df,rows=len(df),ok=True)
