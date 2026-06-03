"""
canonical_report_registry.py — реестр канонических типов отчётов WB.
Определяет тип файла по имени + набору колонок с confidence scoring.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import pandas as pd


@dataclass
class ReportType:
    report_id:        str
    official_name:    str
    domain:           str
    name_patterns:    list[str]
    required_cols:    list[str]
    header_row:       int = 0
    parser_strategy:  str = "generic"
    db_table:         str = "transactions"
    description:      str = ""
    col_count_range:  tuple[int, int] = (0, 9999)


REPORT_REGISTRY: list[ReportType] = [
    ReportType(
        report_id="daily_detailed", official_name="Ежедневный детализированный отчёт",
        domain="sales_intelligence",
        name_patterns=[r"ежедневный.{0,10}детализированный", r"detail.*report"],
        required_cols=["Код номенклатуры","Тип документа","Дата продажи","К перечислению Продавцу за реализованный Товар"],
        parser_strategy="daily_report", db_table="transactions", col_count_range=(75, 95),
    ),
    ReportType(
        report_id="weekly_report", official_name="Еженедельный отчёт",
        domain="finance_intelligence",
        name_patterns=[r"еженедельный", r"weekly.*report"],
        required_cols=["№ отчета","Итого к оплате","Продажа","Стоимость логистики"],
        parser_strategy="weekly", db_table="weekly_reports", col_count_range=(18, 25),
    ),
    ReportType(
        report_id="ad_cost_history", official_name="История затрат (реклама)",
        domain="advertising_intelligence",
        name_patterns=[r"история.{0,5}затрат", r"История-затрат"],
        required_cols=["ID кампании","Кампания","Дата списания","Сумма"],
        parser_strategy="ad_cost", db_table="ad_costs", col_count_range=(6, 10),
    ),
    ReportType(
        report_id="supply_recommendations", official_name="Рекомендации по поставкам",
        domain="warehouse_intelligence",
        name_patterns=[r"recommendation", r"рекомендац"],
        required_cols=["Среднее количество заказов в день в регионе, шт","Потенциальная потеря выручки","Рекомендуем отгрузить"],
        parser_strategy="recommendations", db_table="supply_recommendations", col_count_range=(15, 25),
    ),
    ReportType(
        report_id="warehouse_stocks", official_name="Остатки на складе",
        domain="warehouse_intelligence",
        name_patterns=[r"остатки.{0,10}склад", r"report_\d{4}_\d"],
        required_cols=["Всего находится на складах","В пути до получателей","Объем, л"],
        parser_strategy="stocks", db_table="warehouse_stocks", col_count_range=(10, 60),
    ),
    ReportType(
        report_id="returns", official_name="Возвраты",
        domain="returns_intelligence",
        name_patterns=[r"возврат"],
        required_cols=["Статус","Готов к выдаче","Забрали"],
        header_row=1, parser_strategy="returns", db_table="returns", col_count_range=(14, 22),
    ),
    ReportType(
        report_id="price_template", official_name="Шаблон обновления цен и скидок",
        domain="pricing_intelligence",
        name_patterns=[r"шаблон.{0,10}цен", r"обновлени.{0,5}цен"],
        required_cols=["Текущая цена","Новая цена, RUB","Текущая скидка","Оборачиваемость"],
        parser_strategy="price_template", db_table="price_templates", col_count_range=(12, 18),
    ),
    ReportType(
        report_id="product_catalog", official_name="Каталог товаров (Актуальные остатки)",
        domain="product_intelligence",
        name_patterns=[r"актуальные.{0,5}остатки", r"актуальные_остатки", r"product.{0,5}catalog"],
        required_cols=["Цена закупочная", "Артикул (Код)", "Наименование"],
        parser_strategy="product_catalog", db_table="product_catalog",
        description="Каталог товаров продавца с себестоимостью",
        col_count_range=(10, 50),
    ),
    ReportType(
        report_id="wb_commission_table", official_name="Таблица комиссий WB",
        domain="reference_intelligence",
        name_patterns=[r"commission", r"комисс"],
        required_cols=["Предмет", "Склад WB, %", "Категория"],
        parser_strategy="commission", db_table="wb_commissions",
        description="Базовые ставки ВВ% WB по всем предметам (FBO/FBS)",
        col_count_range=(6, 12),
    ),
    ReportType(
        report_id="product_ratings", official_name="Оценка товара / Рейтинг карточки",
        domain="content_intelligence",
        name_patterns=[r"рейтинг", r"оценк", r"rating"],
        required_cols=["Артикул WB", "Рейтинг карточки", "Рейтинг по отзывам"],
        header_row=1,
        parser_strategy="rating", db_table="product_ratings",
        description="Рейтинг карточек товаров с историей по периодам",
        col_count_range=(20, 35),
    ),
    ReportType(
        report_id="paid_storage", official_name="Платное хранение",
        domain="finance_intelligence",
        name_patterns=[r"платное.{0,5}хранени", r"paid.{0,5}stor"],
        required_cols=["Платное хранение"],
        parser_strategy="storage", db_table="paid_storage", col_count_range=(1, 10),
    ),
]

REGISTRY_BY_ID: dict[str, ReportType] = {r.report_id: r for r in REPORT_REGISTRY}


@dataclass
class CanonicalClassification:
    report_type:   Optional[ReportType]
    confidence:    float
    match_reason:  str
    header_row:    int
    columns:       list[str]
    sample_df:     pd.DataFrame


class CanonicalReportClassifier:
    def classify(self, filepath: Path) -> CanonicalClassification:
        name_lower = filepath.name.lower()
        for candidate in REPORT_REGISTRY:
            df = self._read_sample(filepath, candidate.header_row)
            if df is None:
                continue
            cols = [str(c).strip() for c in df.columns if str(c) not in ("", "nan")]
            col_ok = candidate.col_count_range[0] <= len(cols) <= candidate.col_count_range[1]
            nm = self._match_name(name_lower, candidate.name_patterns)
            cm = self._match_cols(cols, candidate.required_cols)
            if nm and cm and col_ok:
                return CanonicalClassification(candidate, 1.0, "both", candidate.header_row, cols, df)
            if nm and col_ok:
                return CanonicalClassification(candidate, 0.8, "name_pattern", candidate.header_row, cols, df)
            if cm and col_ok:
                return CanonicalClassification(candidate, 0.7, "column_match", candidate.header_row, cols, df)
        df_fb = self._read_sample(filepath, 0)
        cols_fb = [str(c).strip() for c in df_fb.columns] if df_fb is not None else []
        return CanonicalClassification(None, 0.0, "unknown", 0, cols_fb, df_fb or pd.DataFrame())

    @staticmethod
    def _match_name(name: str, patterns: list[str]) -> bool:
        return any(re.search(p, name) for p in patterns)

    @staticmethod
    def _match_cols(cols: list[str], required: list[str]) -> bool:
        cs = {c.strip().lower() for c in cols}
        return any(r.lower() in cs for r in required)

    @staticmethod
    def _read_sample(filepath: Path, header_row: int) -> Optional[pd.DataFrame]:
        try:
            ext = filepath.suffix.lower()
            # ZIP with xlsx inside (rating reports)
            if ext == ".zip":
                import zipfile as _zlib, io as _io
                with _zlib.ZipFile(filepath) as z:
                    xlsx_files = [n for n in z.namelist()
                                  if n.lower().endswith((".xlsx",".xls")) and not n.startswith("__MACOSX")]
                    if xlsx_files:
                        with z.open(xlsx_files[0]) as f:
                            raw = f.read()
                        try:
                            return pd.read_excel(_io.BytesIO(raw), sheet_name="Детализация по артикулам", header=1, nrows=3)
                        except Exception:
                            return pd.read_excel(_io.BytesIO(raw), header=header_row, nrows=3)
                return None
            if ext in (".xlsx", ".xls"):
                # Use xlsx_utils for WB SharedStrings.xml case bug
                try:
                    from core.xlsx_utils import read_excel_safe
                    result = read_excel_safe(filepath, header=header_row, nrows=5)
                    if result is not None:
                        return result
                except ImportError:
                    pass
                for engine in [None, "xlrd"]:
                    try:
                        kw = {"engine": engine} if engine else {}
                        return pd.read_excel(filepath, header=header_row, nrows=5, **kw)
                    except Exception:
                        continue
            elif ext == ".csv":
                try:
                    import chardet
                    enc = chardet.detect(open(filepath,"rb").read(32768)).get("encoding","utf-8")
                except ImportError:
                    enc = "utf-8"
                return pd.read_csv(filepath, header=header_row, nrows=5, encoding=enc)
        except Exception:
            pass
        return None
