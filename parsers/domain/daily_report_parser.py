"""daily_report_parser.py — Ежедневный детализированный отчёт (82 колонки)."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import logging
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult
logger = logging.getLogger(__name__)

_MAP = {
    "Код номенклатуры":"sku_id","Артикул поставщика":"seller_article","Бренд":"brand",
    "Предмет":"category","Название":"product_name","Размер":"size","Баркод":"barcode",
    "Тип документа":"doc_type","Дата заказа покупателем":"order_date","Дата продажи":"sale_date",
    "Кол-во":"quantity","Цена розничная":"retail_price",
    "Вайлдберриз реализовал Товар (Пр)":"wb_sale_price",
    "Размер кВВ, %":"kvv_pct","Итоговый кВВ без НДС, %":"kvv_final_pct",
    "Вознаграждение Вайлдберриз (ВВ), без НДС":"wb_commission",
    "К перечислению Продавцу за реализованный Товар":"seller_payment",
    "Количество доставок":"delivery_count","Количество возврата":"return_count",
    "Услуги по доставке товара покупателю":"delivery_cost","Склад":"warehouse",
    "Номер поставки":"supply_id","Номер офиса":"office_id",
    "Наименование офиса доставки":"office_name","Номер сборочного задания":"assembly_task_id",
    "Тип коробов":"box_type","Srid":"srid","Id корзины заказа":"basket_id",
    "Обоснование для оплаты":"payment_reason","Хранение":"storage_cost",
    "Общая сумма штрафов":"total_penalties","Скидка Wibes, %":"wibes_discount_pct",
    "Скидка по программе софинансирования":"cofinance_discount",
    "Виды логистики, штрафов и корректировок ВВ":"logistics_type",
    "Скидка за промокод, %":"promo_discount_pct","Id подменного артикула":"substitute_sku_id",
    "Стикер МП":"marketplace_sticker","ИНН партнера":"partner_inn","Партнер":"partner_name",
    "Страна":"country",
}

class DailyReportParser(BaseDomainParser):
    report_id="daily_detailed"; domain="sales_intelligence"; db_table="transactions"

    def parse(self, filepath: Path, header_row: int = 0) -> DomainParseResult:
        df = self._read(filepath, header_row)
        if df is None:
            return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
                db_table=self.db_table,df=pd.DataFrame(),rows=0,ok=False,errors=[f"Cannot read {filepath.name}"])
        df = df.rename(columns={k:v for k,v in _MAP.items() if k in df.columns})
        for c in ["quantity","delivery_count","return_count"]:
            if c in df.columns: df[c] = pd.to_numeric(df[c],errors="coerce").fillna(0).astype(int)
        for c in ["retail_price","wb_sale_price","seller_payment","wb_commission","delivery_cost",
                  "storage_cost","total_penalties","kvv_pct","kvv_final_pct","wibes_discount_pct"]:
            if c in df.columns: df[c] = pd.to_numeric(df[c],errors="coerce").fillna(0.0)
        for c in ["order_date","sale_date"]:
            if c in df.columns: df[c] = pd.to_datetime(df[c],errors="coerce")
        pf=pt=None
        if "sale_date" in df.columns:
            vd=df["sale_date"].dropna()
            if not vd.empty: pf,pt=str(vd.min().date()),str(vd.max().date())
        df["report_type"]=self.report_id
        logger.info(f"[daily] Parsed {len(df)} rows from {filepath.name}")
        return DomainParseResult(report_id=self.report_id,filepath=filepath,domain=self.domain,
            db_table=self.db_table,df=df,rows=len(df),ok=True,period_from=pf,period_to=pt)
