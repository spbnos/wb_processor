"""
api/routes/products.py — Матрица товаров.

Единый canonical record на каждый SKU с обогащением из всех источников:
  - price_templates  → цена, скидка, оборачиваемость
  - product_catalog  → себестоимость, габариты
  - warehouse_stocks → FBO остатки по складам
  - supply_recs      → дни остатка, риск
  - transactions     → продажи, комиссия факт
  + расчётные поля: unit_margin, logistics_estimate, breakeven

GET /products/matrix          — полная матрица (фильтры: brand, category, sku)
GET /products/matrix/{sku_id} — один товар полностью
GET /products/brands           — список брендов
GET /products/categories       — список категорий с ВВ%
POST /products/cost             — обновить себестоимость вручную (patch)
GET /products/export            — CSV выгрузка
"""
from __future__ import annotations
import json, logging
from pathlib import Path
from typing import Optional, Any
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
import io
from api.auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["products"])

_DATA = Path(__file__).resolve().parents[2] / "data" / "loaded"
_MANUAL_COSTS = Path(__file__).resolve().parents[2] / "data" / "manual_costs.json"


# ── WB Commission rates (from Оферта 2024-2025) ──────────────────────────────
# Базовые ставки ВВ% FBO (без НДС) по категориям
# Loaded from wb_commissions.json at runtime (from commission.xlsx)
_COMM_CACHE: dict[str, dict] | None = None

def _get_wb_rates(subject: str, category: str = "") -> dict:
    """Lookup real WB commission rates from loaded table."""
    global _COMM_CACHE
    if _COMM_CACHE is None:
        comm_path = _DATA.parent / "data" / "wb_commissions.json"
        if not comm_path.exists():
            comm_path = _DATA / "wb_commissions.json"
        _COMM_CACHE = {}
        if comm_path.exists():
            try:
                rows = json.loads(comm_path.read_bytes())
                for r in rows:
                    subj = str(r.get("subject","")).strip().lower()
                    if subj:
                        _COMM_CACHE[subj] = r
            except Exception:
                pass
    subj_key = subject.strip().lower() if subject else ""
    r = _COMM_CACHE.get(subj_key, {})
    if not r and category:
        # Fallback: find by category
        for row in _COMM_CACHE.values():
            if str(row.get("category","")).lower() == category.lower():
                r = row; break
    fbo = float(r.get("fbo_pct",0) or 15.0)
    fbs = float(r.get("fbs_wb_pct",0) or fbo)
    return {"fbo_pct": fbo or 15.0, "fbs_pct": fbs or 15.0, "source": "wb_table" if r else "default"}

# Legacy hardcoded rates as fallback
WB_COMMISSION_RATES: dict[str, dict] = {
    # Бижутерия и аксессуары
    "Браслеты":          {"fbo_pct": 17.0, "fbs_pct": 17.0},
    "Броши":             {"fbo_pct": 17.0, "fbs_pct": 17.0},
    "Серьги":            {"fbo_pct": 17.0, "fbs_pct": 17.0},
    "Кольца":            {"fbo_pct": 17.0, "fbs_pct": 17.0},
    "Колье":             {"fbo_pct": 17.0, "fbs_pct": 17.0},
    "Цепочки":           {"fbo_pct": 17.0, "fbs_pct": 17.0},
    "Подвески":          {"fbo_pct": 17.0, "fbs_pct": 17.0},
    "Чётки":             {"fbo_pct": 17.0, "fbs_pct": 17.0},
    # Бытовая техника
    "Блендеры":          {"fbo_pct": 13.0, "fbs_pct": 13.0},
    "Вентиляторы":       {"fbo_pct": 13.0, "fbs_pct": 13.0},
    "Вафельницы":        {"fbo_pct": 13.0, "fbs_pct": 13.0},
    "Водонагреватели":   {"fbo_pct": 13.0, "fbs_pct": 13.0},
    "Выпрямители волос": {"fbo_pct": 13.0, "fbs_pct": 13.0},
    "Пылесосы":          {"fbo_pct": 13.0, "fbs_pct": 13.0},
    "Термосы":           {"fbo_pct": 13.0, "fbs_pct": 13.0},
    "Массажеры электрические": {"fbo_pct": 15.0, "fbs_pct": 15.0},
    "Аппараты для маникюра и педикюра": {"fbo_pct": 15.0, "fbs_pct": 15.0},
    "Бритвы электрические": {"fbo_pct": 15.0, "fbs_pct": 15.0},
    # Посуда и кухня
    "Вазы":              {"fbo_pct": 15.0, "fbs_pct": 15.0},
    "Вилки столовые":    {"fbo_pct": 15.0, "fbs_pct": 15.0},
    # Хранение и порядок
    "Вешалки-плечики":   {"fbo_pct": 15.0, "fbs_pct": 15.0},
    "Лотки для приборов":{"fbo_pct": 15.0, "fbs_pct": 15.0},
    # Освещение
    "Гирлянды интерьерные": {"fbo_pct": 15.0, "fbs_pct": 15.0},
    # Default
    "_default":          {"fbo_pct": 15.0, "fbs_pct": 15.0},
}

# WB Logistics estimate (FBO, руб.) by volume liters
# Source: WB Оферта тарифы 2024
def _estimate_logistics_fbo(volume_l: float, in_zone: bool = True) -> float:
    """Расчётная стоимость логистики FBO на основе объёма товара."""
    if volume_l <= 0:
        return 60.0  # минимум
    if volume_l <= 0.5:  return 60.0
    if volume_l <= 1.0:  return 80.0
    if volume_l <= 2.0:  return 100.0
    if volume_l <= 5.0:  return 150.0
    if volume_l <= 10.0: return 220.0
    if volume_l <= 20.0: return 320.0
    return 500.0

def _estimate_logistics_fbs(volume_l: float) -> float:
    """Расчётная стоимость логистики FBS."""
    if volume_l <= 0: return 75.0
    if volume_l <= 0.5:  return 75.0
    if volume_l <= 1.0:  return 100.0
    if volume_l <= 2.0:  return 130.0
    if volume_l <= 5.0:  return 180.0
    return 280.0


# ── Data helpers ──────────────────────────────────────────────────────────────

def _load(table: str) -> list[dict]:
    p = _DATA / f"{table}.json"
    if not p.exists(): return []
    try: return json.loads(p.read_bytes())
    except: return []

def _load_manual_costs() -> dict[str, float]:
    if not _MANUAL_COSTS.exists(): return {}
    try: return json.loads(_MANUAL_COSTS.read_bytes())
    except: return {}

def _s(v) -> str:
    if v is None: return ""
    s = str(v).strip()
    return "" if s in ("nan","None","NaT","null") else s

def _f(v) -> float:
    try:
        if v is None: return 0.0
        return float(v) or 0.0
    except: return 0.0


# ── Build product matrix ──────────────────────────────────────────────────────

def _build_matrix() -> list[dict]:
    """
    Собирает единую запись на каждый SKU из всех источников.
    Primary key: sku_id (nmID).
    """
    manual_costs = _load_manual_costs()
    matrix: dict[str, dict] = {}

    # ── 1. Seed from price_templates (most complete product list) ──
    for r in _load("price_templates"):
        sku = _s(r.get("sku_id")) or _s(r.get("seller_article"))
        if not sku: continue
        if sku not in matrix:
            matrix[sku] = {
                "sku_id":         _s(r.get("sku_id")),
                "seller_article": _s(r.get("seller_article")),
                "barcode":        _s(r.get("barcode")),
                "brand":          _s(r.get("brand")),
                "category":       _s(r.get("category")),
                "product_name":   "",
                # Price & discount
                "current_price":       _f(r.get("current_price")),
                "current_discount_pct":_f(r.get("current_discount_pct")),
                "discounted_price":    _f(r.get("discounted_price")),
                "new_price":           _f(r.get("new_price")),
                "new_discount_pct":    _f(r.get("new_discount_pct")),
                # Stock from template
                "stock_wb":      _f(r.get("stock_wb")),
                "stock_seller":  _f(r.get("stock_seller")),
                "turnover_days": _f(r.get("turnover_days")),
                # Dimensions (will be filled from product_catalog)
                "weight_kg": 0.0, "width_cm": 0.0, "height_cm": 0.0,
                "length_cm": 0.0, "volume_l": 0.0,
                # Cost
                "cost_price": 0.0,
                # FBO stocks (from warehouse_stocks)
                "fbo_total":              0.0,
                "in_transit_to_customer": 0.0,
                "in_transit_returns":     0.0,
                "fbo_by_warehouse":       {},
                # Supply
                "days_of_stock":      0.0,
                "avg_orders_per_day": 0.0,
                "stock_risk":         "unknown",
                "rec_supply_28d":     0.0,
                # Sales (from transactions)
                "units_sold":         0,
                "revenue_total":      0.0,
                "avg_sell_price":     0.0,
                "kvv_pct_fact":       0.0,
                "logistics_cost_fact":0.0,
                # Commission from Оферта
                "kvv_fbo_pct": 0.0,
                "kvv_fbs_pct": 0.0,
                # Calculated
                "logistics_fbo_est":   0.0,
                "logistics_fbs_est":   0.0,
                "unit_margin_fbo":     0.0,
                "unit_margin_fbs":     0.0,
                "unit_margin_pct_fbo": 0.0,
                "breakeven_price_fbo": 0.0,
                "roi_pct":             0.0,
                # Meta
                "data_sources": ["price_template"],
                # Ratings (from product_ratings)
                "card_rating":     0.0,
                "review_rating":   0.0,
                "reviews_total":   0,
                "buyout_pct_fact": 0.0,
                "orders_qty":      0,
                "is_hidden":       False,
                "rating_period":   "",
                # Subject
                "subject":         _s(r.get("category","")),
            }

    # ── 2. Enrich from product_catalog (cost_price + dimensions) ──
    for r in _load("product_catalog"):
        sku = _s(r.get("sku_id"))
        art = _s(r.get("seller_article"))
        key = sku or art
        if not key: continue
        # Find matching record
        target = matrix.get(sku) or matrix.get(art)
        if target is None:
            # New product (not in price template)
            matrix[key] = {
                "sku_id": sku, "seller_article": art,
                "barcode": _s(r.get("barcode")),
                "brand": _s(r.get("brand")),
                "category": _s(r.get("category") or r.get("subject")),
                "product_name": _s(r.get("product_name")),
                "current_price":0.0,"current_discount_pct":0.0,"discounted_price":0.0,
                "new_price":0.0,"new_discount_pct":0.0,
                "stock_wb":0.0,"stock_seller":_f(r.get("stock_seller")),"turnover_days":0.0,
                "weight_kg":0.0,"width_cm":0.0,"height_cm":0.0,"length_cm":0.0,"volume_l":0.0,
                "cost_price":0.0,
                "fbo_total":0.0,"in_transit_to_customer":0.0,"in_transit_returns":0.0,
                "fbo_by_warehouse":{},"days_of_stock":0.0,"avg_orders_per_day":0.0,
                "stock_risk":"unknown","rec_supply_28d":0.0,
                "units_sold":0,"revenue_total":0.0,"avg_sell_price":0.0,
                "kvv_pct_fact":0.0,"logistics_cost_fact":0.0,
                "kvv_fbo_pct":0.0,"kvv_fbs_pct":0.0,
                "logistics_fbo_est":0.0,"logistics_fbs_est":0.0,
                "unit_margin_fbo":0.0,"unit_margin_fbs":0.0,
                "unit_margin_pct_fbo":0.0,"breakeven_price_fbo":0.0,"roi_pct":0.0,
                "data_sources":["product_catalog"],
            }
            target = matrix[key]
        # Fill dimensions + cost
        if _f(r.get("cost_price")) > 0:
            target["cost_price"] = _f(r.get("cost_price"))
        if _f(r.get("weight_kg")) > 0: target["weight_kg"] = _f(r.get("weight_kg"))
        if _f(r.get("width_cm"))  > 0: target["width_cm"]  = _f(r.get("width_cm"))
        if _f(r.get("height_cm")) > 0: target["height_cm"] = _f(r.get("height_cm"))
        if _f(r.get("length_cm")) > 0: target["length_cm"] = _f(r.get("length_cm"))
        if _f(r.get("volume"))    > 0: target["volume_l"]  = _f(r.get("volume"))
        if not target.get("product_name") and r.get("product_name"):
            target["product_name"] = _s(r.get("product_name"))
        if "product_catalog" not in target["data_sources"]:
            target["data_sources"].append("product_catalog")

    # ── 3. Manual cost overrides ──
    for sku, cost in manual_costs.items():
        if sku in matrix:
            matrix[sku]["cost_price"] = float(cost)
            if "manual_cost" not in matrix[sku]["data_sources"]:
                matrix[sku]["data_sources"].append("manual_cost")

    # ── 4. FBO stocks from warehouse_stocks ──
    for r in _load("warehouse_stocks"):
        sku = _s(r.get("sku_id"))
        art = _s(r.get("seller_article"))
        target = matrix.get(sku) or matrix.get(art)
        if target is None: continue
        wh   = _s(r.get("warehouse_name")) or "Основной"
        qty  = _f(r.get("quantity", 0))
        target["fbo_total"]              += qty
        target["in_transit_to_customer"] += _f(r.get("in_transit_to_customer", 0))
        target["in_transit_returns"]     += _f(r.get("in_transit_returns", 0))
        if qty > 0:
            target["fbo_by_warehouse"][wh] = target["fbo_by_warehouse"].get(wh, 0) + qty
        # Compute volume from warehouse data if missing
        if target["volume_l"] == 0 and _f(r.get("volume_l")) > 0:
            target["volume_l"] = _f(r.get("volume_l"))
        if "warehouse_stocks" not in target["data_sources"]:
            target["data_sources"].append("warehouse_stocks")

    # ── 5. Supply risk from recommendations ──
    # Aggregate per sku (multiple regions)
    supply_by_sku: dict[str, dict] = {}
    for r in _load("supply_recommendations"):
        sku = _s(r.get("sku_id")) or _s(r.get("seller_article"))
        if not sku: continue
        if sku not in supply_by_sku:
            supply_by_sku[sku] = {"days":[], "orders":[], "loss":0.0, "rec28":0.0}
        d = _f(r.get("days_of_stock", 0))
        if d > 0: supply_by_sku[sku]["days"].append(d)
        o = _f(r.get("avg_orders_per_day", 0))
        if o > 0: supply_by_sku[sku]["orders"].append(o)
        supply_by_sku[sku]["loss"] += _f(r.get("potential_revenue_loss_28d", 0))
        supply_by_sku[sku]["rec28"] += _f(r.get("rec_supply_28d", 0))

    for sku, sup in supply_by_sku.items():
        target = matrix.get(sku)
        if target is None: continue
        days = min(sup["days"]) if sup["days"] else 0
        orders = sum(sup["orders"])
        target["days_of_stock"]      = round(days, 1)
        target["avg_orders_per_day"] = round(orders, 2)
        target["rec_supply_28d"]     = round(sup["rec28"], 0)
        if   days <= 7:  target["stock_risk"] = "critical"
        elif days <= 14: target["stock_risk"] = "warning"
        elif days > 0:   target["stock_risk"] = "ok"
        if "supply_recommendations" not in target["data_sources"]:
            target["data_sources"].append("supply_recommendations")

    # ── 6. Sales stats from transactions ──
    tx_by_sku: dict[str, dict] = {}
    for r in _load("transactions"):
        sku = _s(r.get("sku_id") or r.get("sku"))
        if not sku: continue
        if sku not in tx_by_sku:
            tx_by_sku[sku] = {"qty":0,"rev":0.0,"comm":0.0,"logi":0.0,"kvv_sum":0.0,"kvv_cnt":0}
        q = int(_f(r.get("quantity",0)))
        rev = _f(r.get("seller_payment") or r.get("revenue",0))
        comm = abs(_f(r.get("wb_commission") or r.get("commission",0)))
        logi = _f(r.get("delivery_cost") or r.get("logistics",0))
        kvv  = _f(r.get("kvv_final_pct") or r.get("kvv_pct",0))
        tx_by_sku[sku]["qty"]      += q
        tx_by_sku[sku]["rev"]      += rev
        tx_by_sku[sku]["comm"]     += comm
        tx_by_sku[sku]["logi"]     += logi
        if kvv > 0:
            tx_by_sku[sku]["kvv_sum"] += kvv
            tx_by_sku[sku]["kvv_cnt"] += 1

    for sku, tx in tx_by_sku.items():
        target = matrix.get(sku)
        if target is None: continue
        target["units_sold"]          = tx["qty"]
        target["revenue_total"]       = round(tx["rev"],2)
        target["avg_sell_price"]      = round(tx["rev"]/tx["qty"],2) if tx["qty"]>0 else 0.0
        target["logistics_cost_fact"] = round(tx["logi"]/tx["qty"],2) if tx["qty"]>0 else 0.0
        if tx["kvv_cnt"]>0:
            target["kvv_pct_fact"] = round(tx["kvv_sum"]/tx["kvv_cnt"],2)
        if "transactions" not in target["data_sources"]:
            target["data_sources"].append("transactions")

    # ── 7a. Enrich from product_ratings (latest period) ──
    ratings_data = _load("product_ratings")
    if ratings_data:
        for r in ratings_data:
            sku = _s(r.get("sku_id",""))
            art = _s(r.get("seller_article",""))
            target = matrix.get(sku) or matrix.get(art)
            if target is None: continue
            target["card_rating"]     = _f(r.get("card_rating"))
            target["review_rating"]   = _f(r.get("review_rating"))
            target["reviews_total"]   = int(_f(r.get("reviews_total",0)))
            target["buyout_pct_fact"] = _f(r.get("buyout_pct",0))
            target["orders_qty"]      = int(_f(r.get("orders_qty",0)))
            target["is_hidden"]       = str(r.get("is_hidden","")).lower() in ("true","да","1","yes")
            target["rating_period"]   = f"{r.get('period_from','')}→{r.get('period_to','')}"
            if "product_ratings" not in target["data_sources"]:
                target["data_sources"].append("product_ratings")

    # ── 7b. Calculate commission + logistics + unit economics ──
    for sku, p in matrix.items():
        cat     = p.get("category","")
        subject = p.get("subject","") or cat
        # Dynamic rates from commission table
        try:
            rates = _get_wb_rates(subject, cat)
        except Exception:
            rates = {"fbo_pct": 15.0, "fbs_pct": 15.0}
        if not rates.get("fbo_pct"):
            fallback = WB_COMMISSION_RATES.get(cat, WB_COMMISSION_RATES["_default"])
            rates["fbo_pct"] = fallback["fbo_pct"]
            rates["fbs_pct"] = fallback["fbs_pct"]
        p["kvv_fbo_pct"] = rates["fbo_pct"]
        p["kvv_fbs_pct"] = rates.get("fbs_pct", rates["fbo_pct"])

        vol = p["volume_l"]
        if vol == 0 and p["weight_kg"] > 0:
            # Estimate volume from weight
            vol = p["weight_kg"] * 1.5
        p["logistics_fbo_est"] = round(_estimate_logistics_fbo(vol), 1)
        p["logistics_fbs_est"] = round(_estimate_logistics_fbs(vol), 1)

        sell_price = p["discounted_price"] or p["current_price"] or p["avg_sell_price"]
        cost = p["cost_price"]
        kvv_fbo = p["kvv_fbo_pct"]
        logi_fbo = p["logistics_fbo_est"]

        if sell_price > 0:
            # FBO unit margin
            wb_payment = sell_price * (1 - kvv_fbo / 100)
            margin_fbo = wb_payment - logi_fbo - cost
            p["unit_margin_fbo"]     = round(margin_fbo, 2)
            p["unit_margin_pct_fbo"] = round(margin_fbo / sell_price * 100, 2)

            # Breakeven price FBO
            if (1 - kvv_fbo/100) > 0:
                p["breakeven_price_fbo"] = round((logi_fbo + cost) / (1 - kvv_fbo/100), 2)

            # ROI
            if cost > 0:
                p["roi_pct"] = round(margin_fbo / cost * 100, 2)

            # FBS unit margin
            logi_fbs = p["logistics_fbs_est"]
            kvv_fbs  = p["kvv_fbs_pct"]
            wb_pay_fbs = sell_price * (1 - kvv_fbs / 100)
            p["unit_margin_fbs"] = round(wb_pay_fbs - logi_fbs - cost, 2)

    # Sort by revenue desc, then by brand
    result = sorted(matrix.values(), key=lambda x: (-x.get("revenue_total",0), x.get("brand","")))
    return result


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/matrix")
async def get_matrix(
    brand:    Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    sku_id:   Optional[str] = Query(None),
    risk:     Optional[str] = Query(None, description="critical|warning|ok|unknown"),
    has_cost: Optional[bool]= Query(None, description="Только с себестоимостью"),
    sort_by:  str           = Query("revenue", description="revenue|margin|stock|days_of_stock|name"),
    limit:    int           = Query(500, le=2000),
    _=Depends(require_auth),
):
    """Полная матрица товаров — все SKU со всеми атрибутами."""
    rows = _build_matrix()

    if brand:    rows = [r for r in rows if r.get("brand","").lower() == brand.lower()]
    if category: rows = [r for r in rows if r.get("category","").lower() == category.lower()]
    if sku_id:   rows = [r for r in rows if r.get("sku_id") == sku_id or r.get("seller_article") == sku_id]
    if risk:     rows = [r for r in rows if r.get("stock_risk") == risk]
    if has_cost is not None:
        rows = [r for r in rows if (r.get("cost_price",0)>0) == has_cost]

    key_map = {
        "revenue":      lambda x: -x.get("revenue_total",0),
        "margin":       lambda x: -x.get("unit_margin_fbo",0),
        "stock":        lambda x: -x.get("fbo_total",0),
        "days_of_stock":lambda x: x.get("days_of_stock",999),
        "name":         lambda x: x.get("product_name","") or x.get("seller_article",""),
    }
    rows.sort(key=key_map.get(sort_by, key_map["revenue"]))

    return {
        "total":  len(rows),
        "items":  rows[:limit],
        "stats": {
            "brands":           len({r.get("brand") for r in rows if r.get("brand")}),
            "categories":       len({r.get("category") for r in rows if r.get("category")}),
            "with_cost":        sum(1 for r in rows if r.get("cost_price",0)>0),
            "with_fbo_stock":   sum(1 for r in rows if r.get("fbo_total",0)>0),
            "critical_risk":    sum(1 for r in rows if r.get("stock_risk")=="critical"),
            "warning_risk":     sum(1 for r in rows if r.get("stock_risk")=="warning"),
            "total_fbo":        round(sum(r.get("fbo_total",0) for r in rows),0),
            "total_in_transit": round(sum(r.get("in_transit_to_customer",0) for r in rows),0),
        }
    }


@router.get("/matrix/{sku_id}")
async def get_product(sku_id: str, _=Depends(require_auth)):
    """Один товар полностью."""
    rows = _build_matrix()
    for r in rows:
        if r.get("sku_id") == sku_id or r.get("seller_article") == sku_id:
            return r
    return {"error": f"SKU {sku_id!r} not found"}


@router.get("/brands")
async def get_brands(_=Depends(require_auth)):
    rows = _build_matrix()
    brands: dict[str, dict] = {}
    for r in rows:
        b = r.get("brand","—") or "—"
        if b not in brands:
            brands[b] = {"brand":b,"skus":0,"revenue":0.0,"fbo_stock":0}
        brands[b]["skus"]     += 1
        brands[b]["revenue"]  += r.get("revenue_total",0)
        brands[b]["fbo_stock"]+= int(r.get("fbo_total",0))
    return sorted(brands.values(), key=lambda x:-x["revenue"])


@router.get("/categories")
async def get_categories(_=Depends(require_auth)):
    """Категории с комиссиями WB."""
    rows = _build_matrix()
    cats: dict[str,dict] = {}
    for r in rows:
        c = r.get("category","—") or "—"
        if c not in cats:
            rates = WB_COMMISSION_RATES.get(c, WB_COMMISSION_RATES["_default"])
            cats[c] = {"category":c, "kvv_fbo_pct":rates["fbo_pct"],
                       "kvv_fbs_pct":rates["fbs_pct"], "skus":0, "revenue":0.0}
        cats[c]["skus"]    += 1
        cats[c]["revenue"] += r.get("revenue_total",0)
    return sorted(cats.values(), key=lambda x:-x["revenue"])


@router.post("/cost")
async def update_cost(
    sku_id: str = Query(...),
    cost_price: float = Query(..., gt=0),
    _=Depends(require_auth),
):
    """Обновить себестоимость вручную (ручной ввод без файла)."""
    costs = _load_manual_costs()
    costs[sku_id] = cost_price
    _MANUAL_COSTS.parent.mkdir(parents=True, exist_ok=True)
    _MANUAL_COSTS.write_text(json.dumps(costs, ensure_ascii=False, indent=2), "utf-8")
    return {"sku_id": sku_id, "cost_price": cost_price, "saved": True}


@router.get("/export")
async def export_csv(_=Depends(require_auth)):
    """Выгрузка матрицы товаров в CSV."""
    rows = _build_matrix()
    fields = [
        "sku_id","seller_article","barcode","brand","category","product_name",
        "current_price","current_discount_pct","discounted_price",
        "cost_price","weight_kg","volume_l",
        "kvv_fbo_pct","kvv_fbs_pct",
        "logistics_fbo_est","logistics_fbs_est",
        "unit_margin_fbo","unit_margin_pct_fbo","unit_margin_fbs",
        "breakeven_price_fbo","roi_pct",
        "fbo_total","in_transit_to_customer","in_transit_returns",
        "stock_wb","stock_seller","turnover_days",
        "days_of_stock","avg_orders_per_day","stock_risk","rec_supply_28d",
        "units_sold","revenue_total","avg_sell_price",
        "kvv_pct_fact","logistics_cost_fact",
        "data_sources",
    ]
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM for Excel
    buf.write(";".join(fields) + "\n")
    for r in rows:
        vals = []
        for f in fields:
            v = r.get(f,"")
            if isinstance(v, list): v = "|".join(str(x) for x in v)
            if isinstance(v, dict): v = json.dumps(v, ensure_ascii=False)
            vals.append(str(v).replace(";","_"))
        buf.write(";".join(vals) + "\n")
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=product_matrix.csv"}
    )
