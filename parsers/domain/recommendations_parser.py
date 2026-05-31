"""recommendations_parser.py — Рекомендации по поставкам."""
from __future__ import annotations
from pathlib import Path
import pandas as pd, logging
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult
logger = logging.getLogger(__name__)
_MAP={"Регион":"region","Склады в регионе":"warehouses","Артикул продавца":"seller_article",
      "Размер":"size","Наименование товара":"product_name","Артикул WB":"sku_id","Баркоды":"barcode",
      "На сколько дней хватит остатков":"days_of_stock","Уровень остатка":"stock_level",
      "Рекомендация":"recommendation",}
_PARTIAL={"Среднее количество заказов в день в регионе, шт":"avg_orders_per_day",
           "Среднее количество заказов в день в регионе (прогнозное)":"avg_orders_forecast",
           "Потенциальная потеря выручки":"potential_revenue_loss_28d",
           "Все запланированные поставки":"planned_supplies",
           "Рекомендуем отгрузить (хватит на 14":"rec_supply_14d","Рекомендуем отгрузить (хватит на 21":"rec_supply_21d",
           "Рекомендуем отгрузить (хватит на 28":"rec_supply_28d","Рекомендуем отгрузить (хватит на 56":"rec_supply_56d",
           "Остаток в регионе":"stock_in_region"}

class RecommendationsParser(BaseDomainParser):
    report_id="supply_recommendations"; domain="warehouse_intelligence"; db_table="supply_recommendations"
    def parse(self, filepath, header_row=0):
        df=self._read(filepath,header_row)
        if df is None:
            return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
                db_table=self.db_table,df=pd.DataFrame(),rows=0,ok=False,errors=[f"Cannot read {filepath.name}"])
        rename={}
        for col in df.columns:
            cs=str(col).strip()
            if cs in _MAP: rename[cs]=_MAP[cs]
            else:
                for prefix,canon in _PARTIAL.items():
                    if cs.startswith(prefix[:20]): rename[cs]=canon; break
        df=df.rename(columns=rename)
        # Deduplicate column names (some WB files have duplicate headers)
        seen_cols = {}
        new_cols = []
        for col in df.columns:
            if col in seen_cols:
                seen_cols[col] += 1
                new_cols.append(f"{col}_{seen_cols[col]}")
            else:
                seen_cols[col] = 0
                new_cols.append(col)
        df.columns = new_cols
        _NUM = ["avg_orders_per_day","avg_orders_forecast","days_of_stock","potential_revenue_loss_28d",
                "planned_supplies","rec_supply_14d","rec_supply_21d","rec_supply_28d","rec_supply_56d","stock_in_region"]
        for c in _NUM:
            if c in df.columns and c in df.columns:
                try:
                    df[c]=pd.to_numeric(df[c],errors="coerce").fillna(0.0)
                except Exception:
                    pass
        df["report_type"]=self.report_id
        logger.info(f"[recommendations] Parsed {len(df)} rows from {filepath.name}")
        return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
            db_table=self.db_table,df=df,rows=len(df),ok=True)
