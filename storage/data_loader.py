"""
DataLoader — сохраняет нормализованный DataFrame в PostgreSQL.

Стратегия upsert:
  - transactions / stocks → insert-only (с дедупликацией по file_id)
  - products            → upsert по sku
  - files               → update статуса

Работает в двух режимах:
  use_db=True  → PostgreSQL через SQLAlchemy
  use_db=False → JSON-файл  (для тестов / разработки без БД)
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from normalizers.normalizer import NormalizeResult
from mapping.mapping_storage import MappingObj

logger = logging.getLogger(__name__)

_DEFAULT_JSON_DIR = Path(__file__).resolve().parent.parent / "data" / "loaded"

# Какие target_field → в какую таблицу
_PRODUCT_FIELDS  = {"sku", "barcode", "name", "brand", "category", "cost_price"}
_TRANS_FIELDS    = {
    "sku", "barcode", "date", "transaction_type", "quantity",
    "price", "revenue", "commission", "logistics", "net_profit",
    "warehouse", "region",
}
_STOCK_FIELDS    = {
    "sku", "barcode", "warehouse", "quantity", "reserved",
    "in_transit", "date",
}


# ─────────────────────────────────────────────────────────
@dataclass
class LoadResult:
    filepath: Path
    mapping_category: str
    rows_total: int
    rows_inserted: int
    rows_updated: int
    rows_skipped: int
    tables_written: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ok: bool = True


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────
def _col(df: pd.DataFrame, name: str, default=None):
    """Безопасно достаёт колонку из DataFrame."""
    if name in df.columns:
        v = df[name]
        return v
    return pd.Series([default] * len(df), name=name)


def _val(row, col: str, default=None):
    """Безопасно достаёт значение из строки."""
    v = row.get(col, default)
    if v is None:
        return default
    try:
        if pd.isna(v):
            return default
    except (TypeError, ValueError):
        pass
    return v


def _to_py(v):
    """Конвертирует pandas/numpy типы в python-native для JSON."""
    if v is None:
        return None
    # pandas Series — берём первый элемент
    if isinstance(v, pd.Series):
        if len(v) == 0:
            return None
        v = v.iloc[0]
    # numpy array
    import numpy as np
    if isinstance(v, np.ndarray):
        if v.size == 0:
            return None
        v = v.flat[0]
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, 'item') and hasattr(v, 'ndim') and v.ndim == 0:
        return v.item()
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


# ─────────────────────────────────────────────────────────
# DataLoader
# ─────────────────────────────────────────────────────────
class DataLoader:
    """
    Использование:
        loader = DataLoader(use_db=True)
        result = loader.load(normalize_result, mapping, file_id=42)
    """

    def __init__(self, use_db: bool = True, json_dir: Path = _DEFAULT_JSON_DIR):
        self._use_db = use_db
        self._json_dir = json_dir
        if not use_db:
            self._json_dir.mkdir(parents=True, exist_ok=True)

    def load(
        self,
        norm_result: NormalizeResult,
        mapping: MappingObj,
        file_id: Optional[int] = None,
        file_hash: Optional[str] = None,
    ) -> LoadResult:

        if not norm_result.ok or norm_result.df.empty:
            return LoadResult(
                filepath=norm_result.filepath,
                mapping_category=mapping.category,
                rows_total=0, rows_inserted=0, rows_updated=0, rows_skipped=0,
                errors=["Skipped: normalize result not ok or empty"],
                ok=False,
            )

        logger.info(
            f"[loader] Loading {norm_result.row_count} rows "
            f"from {norm_result.filepath.name} "
            f"[category={mapping.category}]"
        )

        df = norm_result.df
        category = mapping.category

        if self._use_db:
            return self._load_db(df, mapping, file_id, norm_result.filepath)
        return self._load_json(df, mapping, file_id, norm_result.filepath, file_hash=file_hash)

    # ── DB mode ──────────────────────────────────────────

    def _load_db(
        self,
        df: pd.DataFrame,
        mapping: MappingObj,
        file_id: Optional[int],
        filepath: Path,
    ) -> LoadResult:

        from db.database import SessionLocal
        from db.models import Product, Transaction, Stock, File

        inserted = updated = skipped = 0
        tables: list[str] = []
        errors: list[str] = []
        category = mapping.category

        with SessionLocal() as db:
            try:
                # ── Products (если есть sku) ──────────────
                if "sku" in df.columns:
                    ins, upd, skip = self._upsert_products_db(db, df)
                    inserted += ins; updated += upd; skipped += skip
                    if ins or upd:
                        tables.append("products")

                # ── Transactions ──────────────────────────
                if category in ("wb_report",) and "sku" in df.columns:
                    ins, skip = self._insert_transactions_db(db, df, file_id)
                    inserted += ins; skipped += skip
                    if ins:
                        tables.append("transactions")

                # ── Stocks ────────────────────────────────
                if category == "external" and mapping.subcategory in ("stocks", None):
                    if "sku" in df.columns and "quantity" in df.columns:
                        ins, skip = self._insert_stocks_db(db, df, file_id)
                        inserted += ins; skipped += skip
                        if ins:
                            tables.append("stocks")

                db.commit()
                logger.info(f"[loader] Committed: +{inserted} ins, ~{updated} upd, -{skipped} skip")

            except Exception as e:
                db.rollback()
                errors.append(str(e))
                logger.error(f"[loader] DB error: {e}", exc_info=True)
                return LoadResult(
                    filepath=filepath, mapping_category=mapping.category,
                    rows_total=len(df), rows_inserted=0, rows_updated=0,
                    rows_skipped=len(df), tables_written=[],
                    errors=errors, ok=False,
                )

        return LoadResult(
            filepath=filepath, mapping_category=mapping.category,
            rows_total=len(df), rows_inserted=inserted,
            rows_updated=updated, rows_skipped=skipped,
            tables_written=tables, errors=errors, ok=True,
        )

    def _upsert_products_db(self, db, df: pd.DataFrame):
        from db.models import Product
        inserted = updated = skipped = 0

        for _, row in df.iterrows():
            sku = _val(row, "sku")
            if not sku:
                skipped += 1
                continue

            existing = db.query(Product).filter_by(sku=str(sku)).first()
            if existing:
                # Обновляем только непустые поля
                for col in ("name", "brand", "category", "barcode", "cost_price"):
                    v = _val(row, col)
                    if v is not None:
                        setattr(existing, col, v)
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                product = Product(
                    sku=str(sku),
                    barcode=str(_val(row, "barcode", "")) or None,
                    name=_val(row, "name"),
                    brand=_val(row, "brand"),
                    category=_val(row, "category"),
                    cost_price=_val(row, "cost_price"),
                )
                db.add(product)
                inserted += 1

        return inserted, updated, skipped

    def _insert_transactions_db(self, db, df: pd.DataFrame, file_id: Optional[int]):
        from db.models import Transaction
        inserted = skipped = 0

        for _, row in df.iterrows():
            sku = _val(row, "sku")
            if not sku:
                skipped += 1
                continue
            t = Transaction(
                file_id=file_id,
                sku=str(sku),
                barcode=str(_val(row, "barcode", "")) or None,
                transaction_date=_val(row, "date"),
                transaction_type=_val(row, "transaction_type", "sale"),
                quantity=_val(row, "quantity"),
                price=_val(row, "price"),
                revenue=_val(row, "revenue"),
                commission=_val(row, "commission"),
                logistics=_val(row, "logistics"),
                net_profit=_val(row, "net_profit"),
                warehouse=_val(row, "warehouse"),
                region=_val(row, "region"),
                extra={
                    col: _to_py(row[col])
                    for col in df.columns
                    if col not in _TRANS_FIELDS and col in row
                } or None,
            )
            db.add(t)
            inserted += 1

        return inserted, skipped

    def _insert_stocks_db(self, db, df: pd.DataFrame, file_id: Optional[int]):
        from db.models import Stock
        inserted = skipped = 0

        for _, row in df.iterrows():
            sku = _val(row, "sku")
            if not sku:
                skipped += 1
                continue

            qty = _val(row, "quantity", 0)
            try:
                qty = int(qty) if qty is not None else 0
            except (TypeError, ValueError):
                qty = 0

            s = Stock(
                file_id=file_id,
                sku=str(sku),
                barcode=str(_val(row, "barcode", "")) or None,
                warehouse=_val(row, "warehouse"),
                quantity=qty,
                reserved=_val(row, "reserved", 0) or 0,
                in_transit=_val(row, "in_transit", 0) or 0,
                report_date=_val(row, "date"),
                extra={
                    col: _to_py(row[col])
                    for col in df.columns
                    if col not in _STOCK_FIELDS and col in row
                } or None,
            )
            db.add(s)
            inserted += 1

        return inserted, skipped

    # ── JSON mode ─────────────────────────────────────────

    def _json_already_loaded(self, path: Path, file_hash: Optional[str], file_id: Optional[int]) -> bool:
        if not path.exists():
            return False
        existing = self._load_json_file(path)
        if file_hash:
            return any(e.get("file_hash") == file_hash for e in existing)
        if file_id:
            return any(e.get("file_id") == file_id for e in existing)
        return False

    def _load_json(
        self,
        df: pd.DataFrame,
        mapping: MappingObj,
        file_id: Optional[int],
        filepath: Path,
        file_hash: Optional[str] = None,
    ) -> LoadResult:

        category = mapping.category
        subcategory = mapping.subcategory or ""
        tables: list[str] = []
        inserted = skipped = updated = 0

        rows = [
            {col: _to_py(row[col]) for col in df.columns}
            for _, row in df.iterrows()
        ]

        # Products
        if "sku" in df.columns:
            prod_path = self._json_dir / "products.json"
            existing = self._load_json_file(prod_path)
            sku_map = {p["sku"]: i for i, p in enumerate(existing)}

            for row in rows:
                sku = row.get("sku")
                if not sku:
                    skipped += 1
                    continue
                prod_data = {k: row.get(k) for k in _PRODUCT_FIELDS if k in row}
                prod_data["sku"] = sku
                prod_data["updated_at"] = datetime.utcnow().isoformat()

                if sku in sku_map:
                    existing[sku_map[sku]].update({k: v for k, v in prod_data.items() if v is not None})
                    updated += 1
                else:
                    prod_data["created_at"] = datetime.utcnow().isoformat()
                    existing.append(prod_data)
                    inserted += 1

            self._save_json_file(prod_path, existing)
            tables.append("products")

        # Transactions
        if category == "wb_report":
            trans_path = self._json_dir / "transactions.json"
            if not self._json_already_loaded(trans_path, file_hash, file_id):
                existing = self._load_json_file(trans_path)
                count_before = len(existing)
                for row in rows:
                    sku = row.get("sku")
                    if not sku:
                        skipped += 1
                        continue
                    entry = {k: row.get(k) for k in _TRANS_FIELDS if k in row}
                    entry["file_id"] = file_id
                    entry["file_hash"] = file_hash
                    entry["created_at"] = datetime.utcnow().isoformat()
                    existing.append(entry)
                self._save_json_file(trans_path, existing)
                new_ins = len(existing) - count_before
                inserted += new_ins
                tables.append("transactions")
            else:
                logger.info(f"[loader][json] Skip duplicate transactions for {filepath.name}")

        # Stocks
        if category == "external" and "quantity" in df.columns and "sku" in df.columns:
            stocks_path = self._json_dir / "stocks.json"
            if not self._json_already_loaded(stocks_path, file_hash, file_id):
                existing = self._load_json_file(stocks_path)
                count_before = len(existing)
                for row in rows:
                    sku = row.get("sku")
                    if not sku:
                        skipped += 1
                        continue
                    entry = {k: row.get(k) for k in _STOCK_FIELDS if k in row}
                    entry["file_id"] = file_id
                    entry["file_hash"] = file_hash
                    entry["created_at"] = datetime.utcnow().isoformat()
                    existing.append(entry)
                self._save_json_file(stocks_path, existing)
                new_ins = len(existing) - count_before
                inserted += new_ins
                tables.append("stocks")
            else:
                logger.info(f"[loader][json] Skip duplicate stocks for {filepath.name}")

        logger.info(f"[loader][json] +{inserted} ins, ~{updated} upd, -{skipped} skip → {tables}")

        return LoadResult(
            filepath=filepath, mapping_category=category,
            rows_total=len(df), rows_inserted=inserted,
            rows_updated=updated, rows_skipped=skipped,
            tables_written=tables, ok=True,
        )

    def _load_json_file(self, path: Path) -> list:
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else []
        except (json.JSONDecodeError, ValueError):
            return []

    def _save_json_file(self, path: Path, data: list):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
