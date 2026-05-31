"""
product_catalog_parser.py — Каталог товаров продавца (Актуальные_остатки_fixed.xlsx).

Этот файл — НЕ складские остатки WB, а КАТАЛОГ продавца из личного кабинета.
Содержит себестоимость (Цена закупочная) — ключевой элемент юнит-экономики.

Canonical table: product_catalog
Join key: sku_id (Артикул (Код) = WB nmID) + barcode
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import logging
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult

logger = logging.getLogger(__name__)

_MAP = {
    "Артикул (Код)":          "sku_id",           # WB nmID
    "Артикул поставщика":     "seller_article",
    "Штрихкод":               "barcode",
    "Наименование":           "product_name",
    "Цена закупочная":        "cost_price",        # ← себестоимость!
    "Остаток":                "stock_seller",      # остаток у продавца (не WB)
    "Бренд":                  "brand",
    "Категория":              "category",
    "Предмет":                "subject",
    "Вес в упаковке":         "weight_kg",
    "Ширина упаковки":        "width_cm",
    "Высота упаковки":        "height_cm",
    "Длина упаковки":         "length_cm",
    "Объем":                  "volume",
    "Цвет":                   "color",
    "Материал":               "material",
    "Страна происхождения":   "country_origin",
    "Количество в комплекте": "qty_in_pack",
    "Ссылка на главное фото": "photo_url",
}


class ProductCatalogParser(BaseDomainParser):
    report_id  = "product_catalog"
    domain     = "product_intelligence"
    db_table   = "product_catalog"
    header_row = 0

    @staticmethod
    def _read_wb_xlsx(filepath) -> "pd.DataFrame | None":
        """Fix case-sensitive SharedStrings.xml bug in WB-exported xlsx files."""
        import io, zipfile
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            with zipfile.ZipFile(io.BytesIO(data)) as zin:
                names = zin.namelist()
                if 'xl/SharedStrings.xml' not in names or 'xl/sharedStrings.xml' in names:
                    return None  # No fix needed
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        raw = zin.read(item.filename)
                        if item.filename in ('xl/workbook.xml', '[Content_Types].xml'):
                            raw = raw.replace(b'SharedStrings.xml', b'sharedStrings.xml')
                        item.filename = item.filename.replace(
                            'xl/SharedStrings.xml', 'xl/sharedStrings.xml')
                        zout.writestr(item, raw)
                buf.seek(0)
                return pd.read_excel(buf)
        except Exception as e:
            logger.debug(f"[product_catalog] _read_wb_xlsx fallback: {e}")
            return None

    def parse(self, filepath: Path, header_row: int = 0) -> DomainParseResult:
        _wb = self._read_wb_xlsx(filepath)
        df = _wb if _wb is not None else self._read(filepath, header_row)
        if df is None:
            return DomainParseResult(
                report_id=self.report_id, filepath=filepath,
                domain=self.domain, db_table=self.db_table,
                df=pd.DataFrame(), rows=0, ok=False,
                errors=[f"Cannot read {filepath.name}"],
            )

        rename = {k: v for k, v in _MAP.items() if k in df.columns}
        df = df.rename(columns=rename)

        # Types
        def _to_id(v):
            if v is None or str(v).strip() in ('','nan','None','NaT'): return None
            s = str(v).strip()
            try: return str(int(float(s)))  # numeric nmID
            except (ValueError, TypeError): return s  # keep as-is (e.g. 'J8166')

        if "sku_id" in df.columns:
            df["sku_id"] = df["sku_id"].apply(_to_id)
        if "barcode" in df.columns:
            df["barcode"] = df["barcode"].apply(_to_id)

        for num_col in ["cost_price", "stock_seller", "weight_kg", "width_cm",
                        "height_cm", "length_cm", "volume", "qty_in_pack"]:
            if num_col in df.columns:
                df[num_col] = pd.to_numeric(df[num_col], errors="coerce")

        # Remove rows with no sku_id AND no barcode (empty rows)
        before = len(df)
        if "sku_id" in df.columns or "barcode" in df.columns:
            mask_sku = df.get("sku_id", pd.Series([None]*len(df))).notna()
            mask_bar = df.get("barcode", pd.Series([None]*len(df))).notna()
            df = df[mask_sku | mask_bar].copy()

        df["report_type"] = self.report_id
        logger.info(
            f"[product_catalog] Parsed {len(df)}/{before} rows from {filepath.name} "
            f"(cost_price: {df['cost_price'].notna().sum() if 'cost_price' in df.columns else 0} non-null)"
        )
        return DomainParseResult(
            report_id=self.report_id, filepath=filepath,
            domain=self.domain, db_table=self.db_table,
            df=df, rows=len(df), ok=True,
        )
