"""
api/routes/analytics.py — бизнес-аналитика.
Поддерживает dual-schema transactions (old: revenue/commission/logistics + new: seller_payment/wb_commission/delivery_cost).
"""
from __future__ import annotations
import json, logging
from pathlib import Path
from typing import Optional, Any
from fastapi import APIRouter, Depends, Query
from api.auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])

_DATA = Path(__file__).resolve().parents[2] / "data" / "loaded"
_REG  = Path(__file__).resolve().parents[2] / "data" / "processed_registry.json"


# ── Data helpers ─────────────────────────────────────────────────────────────

def _load(table: str) -> list[dict]:
    p = _DATA / f"{table}.json"
    if not p.exists(): return []
    try: return json.loads(p.read_bytes())
    except Exception: return []


def _s(v) -> str:
    if v is None: return ""
    s = str(v).strip()
    return "" if s in ("nan","None","NaT","null") else s


def _f(v) -> float:
    try:
        if v is None: return 0.0
        f = float(v)
        return 0.0 if f != f else f  # NaN check
    except: return 0.0


def _get(r: dict, *keys) -> Any:
    """Try multiple field aliases, return first non-null."""
    for k in keys:
        v = r.get(k)
        if v is not None and str(v) not in ("nan","None","NaT",""):
            return v
    return None


# Dual-schema field resolvers
def _rev(r: dict) -> float:
    """Revenue: seller_payment (new) || revenue (old)"""
    return _f(_get(r, "seller_payment", "revenue", "wb_sale_price"))

def _comm(r: dict) -> float:
    """Commission (always positive cost): wb_commission (new) || abs(commission) (old)"""
    v = _f(_get(r, "wb_commission", "commission"))
    return abs(v)  # ensure positive — it's a cost

def _logi(r: dict) -> float:
    """Logistics cost: delivery_cost (new) || logistics (old)"""
    return _f(_get(r, "delivery_cost", "logistics"))

def _stor(r: dict) -> float:
    return _f(_get(r, "storage_cost"))

def _pens(r: dict) -> float:
    return _f(_get(r, "total_penalties"))

def _qty(r: dict) -> int:
    return int(_f(_get(r, "quantity")) or 0)

def _sku(r: dict) -> str:
    return _s(_get(r, "sku_id", "sku"))

def _date(r: dict) -> str:
    """Date: sale_date (new) || date (old) || _period_from"""
    d = _get(r, "sale_date", "date", "_period_from")
    return str(d)[:10] if d else ""


def _filter_period(records: list[dict], date_from: Optional[str], date_to: Optional[str]) -> list[dict]:
    """Filter by date using dual-schema date fields."""
    if not date_from and not date_to:
        return records
    out = []
    for r in records:
        d = _date(r)
        if not d:
            out.append(r); continue
        if date_from and d < date_from: continue
        if date_to   and d > date_to:   continue
        out.append(r)
    return out


def _filter_date_col(records: list[dict], col: str, date_from: Optional[str], date_to: Optional[str]) -> list[dict]:
    """Filter by a specific date column."""
    if not date_from and not date_to:
        return records
    out = []
    for r in records:
        d = str(r.get(col, "") or "")[:10]
        if not d: out.append(r); continue
        if date_from and d < date_from: continue
        if date_to   and d > date_to:   continue
        out.append(r)
    return out


# ── Product catalog JOIN for unit economics ───────────────────────────────────

_catalog_cache: dict[str, dict] | None = None

def _get_catalog() -> dict[str, dict]:
    """Returns {sku_id: {cost_price, brand, category, ...}} from product_catalog."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    data = _load("product_catalog")
    result: dict[str, dict] = {}
    for r in data:
        sku = _s(_get(r, "sku_id"))
        if sku:
            result[sku] = {
                "cost_price":     _f(r.get("cost_price")),
                "seller_article": _s(r.get("seller_article")),
                "brand":          _s(r.get("brand")),
                "category":       _s(r.get("category") or r.get("subject")),
                "product_name":   _s(r.get("product_name")),
                "barcode":        _s(r.get("barcode")),
            }
    _catalog_cache = result
    return result


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/summary")
async def summary(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    _=Depends(require_auth),
):
    tx   = _filter_period(_load("transactions"),  date_from, date_to)
    wkly = _filter_date_col(_load("weekly_reports"), "period_start", date_from, date_to)
    cat  = _get_catalog()

    rev  = sum(_rev(r) for r in tx)
    comm = sum(_comm(r) for r in tx)
    logi = sum(_logi(r) for r in tx)
    stor = sum(_stor(r) for r in tx)
    pens = sum(_pens(r) for r in tx)
    qty  = sum(_qty(r) for r in tx)
    rets = sum(int(_f(_get(r, "return_count"))) for r in tx)
    net  = rev - comm - logi - stor - pens

    # Unit economics: cost from catalog
    cost_total = 0.0
    for r in tx:
        sku = _sku(r)
        cp = cat.get(sku, {}).get("cost_price", 0.0) or 0.0
        cost_total += cp * _qty(r)

    unit_net = net - cost_total

    # Fallback to weekly_reports if no transactions
    if not tx and wkly:
        rev  = sum(_f(r.get("sales_amount"))    for r in wkly)
        logi = sum(_f(r.get("logistics_cost"))  for r in wkly)
        stor = sum(_f(r.get("storage_cost"))    for r in wkly)
        pens = sum(_f(r.get("total_penalties")) for r in wkly)
        net  = sum(_f(r.get("total_payable"))   for r in wkly)

    # Brand/category breakdown
    brand_rev: dict[str, float] = {}
    cat_rev:   dict[str, float] = {}
    for r in tx:
        brand = _s(_get(r, "brand")) or (cat.get(_sku(r), {}).get("brand") or "—")
        categ = _s(_get(r, "category")) or (cat.get(_sku(r), {}).get("category") or "—")
        v = _rev(r)
        brand_rev[brand] = brand_rev.get(brand, 0.0) + v
        cat_rev[categ]   = cat_rev.get(categ,  0.0) + v

    # Actual date range from data
    all_dates = sorted({_date(r) for r in tx if _date(r)})
    pf = all_dates[0]  if all_dates else (date_from or "")
    pt = all_dates[-1] if all_dates else (date_to   or "")

    skus = {_sku(r) for r in tx if _sku(r)}
    loaded = [p.stem for p in _DATA.glob("*.json") if p.stat().st_size > 100] if _DATA.exists() else []

    return {
        # Actual data period (not filter period)
        "period_from":       pf,
        "period_to":         pt,
        "filter_from":       date_from or "",
        "filter_to":         date_to   or "",
        # Revenue
        "total_revenue":     round(rev,  2),
        "total_commission":  round(comm, 2),
        "total_logistics":   round(logi, 2),
        "total_storage":     round(stor, 2),
        "total_penalties":   round(pens, 2),
        "total_cost":        round(cost_total, 2),
        "net_profit":        round(net,  2),
        "unit_net_profit":   round(unit_net, 2),
        # Counts
        "sales_count":       qty,
        "returns_count":     rets,
        "unique_skus":       len(skus),
        # Percentages
        "avg_margin_pct":    round(net / rev * 100, 2) if rev > 0 else 0.0,
        "unit_margin_pct":   round(unit_net / rev * 100, 2) if rev > 0 else 0.0,
        # Top lists
        "top_brands":     [{"brand":k,"revenue":round(v,2)}
                           for k,v in sorted(brand_rev.items(),key=lambda x:-x[1])[:8]],
        "top_categories": [{"category":k,"revenue":round(v,2)}
                           for k,v in sorted(cat_rev.items(),key=lambda x:-x[1])[:8]],
        "domains_loaded":    loaded,
    }


@router.get("/sales")
async def sales(
    date_from:   Optional[str] = Query(None),
    date_to:     Optional[str] = Query(None),
    brand:       Optional[str] = Query(None),
    category:    Optional[str] = Query(None),
    sku_id:      Optional[str] = Query(None),
    group_by:    str           = Query("brand", description="brand|category|sku|date"),
    limit:       int           = Query(100, le=500),
    _=Depends(require_auth),
):
    tx  = _filter_period(_load("transactions"), date_from, date_to)
    cat = _get_catalog()

    if brand:    tx = [r for r in tx if (_s(_get(r,"brand")) or cat.get(_sku(r),{}).get("brand","")).lower() == brand.lower()]
    if category: tx = [r for r in tx if (_s(_get(r,"category")) or cat.get(_sku(r),{}).get("category","")).lower() == category.lower()]
    if sku_id:   tx = [r for r in tx if _sku(r) == sku_id]

    agg: dict[str, dict] = {}
    for r in tx:
        sku  = _sku(r)
        info = cat.get(sku, {})
        b    = _s(_get(r,"brand"))     or info.get("brand","—")    or "—"
        c    = _s(_get(r,"category"))  or info.get("category","—") or "—"
        nm   = _s(_get(r,"product_name")) or info.get("product_name","")
        sa   = _s(_get(r,"seller_article")) or info.get("seller_article","")
        dt   = _date(r)[:10]
        cp   = info.get("cost_price", 0.0) or 0.0

        if group_by == "brand":      key = b
        elif group_by == "category": key = c
        elif group_by == "date":     key = dt
        else:                        key = sku or "—"

        if key not in agg:
            agg[key] = {
                "sku_id": sku, "seller_article": sa, "brand": b,
                "category": c, "product_name": nm,
                "quantity":0, "revenue":0.0, "commission":0.0,
                "logistics":0.0, "storage":0.0, "penalties":0.0,
                "cost":0.0, "net_profit":0.0, "unit_margin":0.0,
                "return_count":0,
            }
        q = _qty(r)
        v = _rev(r)
        agg[key]["quantity"]     += q
        agg[key]["revenue"]      += v
        agg[key]["commission"]   += _comm(r)
        agg[key]["logistics"]    += _logi(r)
        agg[key]["storage"]      += _stor(r)
        agg[key]["penalties"]    += _pens(r)
        agg[key]["cost"]         += cp * q
        agg[key]["return_count"] += int(_f(_get(r,"return_count")))

    for v in agg.values():
        gross = v["revenue"] - v["commission"] - v["logistics"] - v["storage"] - v["penalties"]
        v["net_profit"]   = round(gross, 2)
        v["unit_margin"]  = round(gross - v["cost"], 2)
        v["margin_pct"]   = round(v["unit_margin"] / v["revenue"] * 100, 2) if v["revenue"] > 0 else 0.0
        for k in ["revenue","commission","logistics","storage","penalties","cost"]:
            v[k] = round(v[k], 2)

    rows = sorted(agg.values(), key=lambda x: -x["revenue"])[:limit]
    return rows


@router.get("/finance")
async def finance(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    _=Depends(require_auth),
):
    data = _filter_date_col(_load("weekly_reports"), "period_start", date_from, date_to)
    result = []
    for r in sorted(data, key=lambda x: str(x.get("period_start",""))):
        result.append({
            "report_number":  _s(r.get("report_number")),
            "period_start":   str(r.get("period_start",""))[:10],
            "period_end":     str(r.get("period_end",""))[:10],
            "sales_amount":   round(_f(r.get("sales_amount")),2),
            "seller_payment": round(_f(r.get("seller_payment")),2),
            "logistics_cost": round(_f(r.get("logistics_cost")),2),
            "storage_cost":   round(_f(r.get("storage_cost")),2),
            "total_penalties":round(_f(r.get("total_penalties")),2),
            "total_payable":  round(_f(r.get("total_payable")),2),
            "acceptance_cost":round(_f(r.get("acceptance_cost")),2),
            "loyalty_cost":   round(_f(r.get("loyalty_cost")),2),
        })
    return result


@router.get("/stocks")
async def stocks(
    brand:     Optional[str] = Query(None),
    category:  Optional[str] = Query(None),
    warehouse: Optional[str] = Query(None),
    min_qty:   float         = Query(0),
    _=Depends(require_auth),
):
    data = _load("warehouse_stocks")
    cat  = _get_catalog()

    if brand:     data = [r for r in data if _s(r.get("brand","")).lower() == brand.lower()]
    if category:  data = [r for r in data if _s(r.get("category","")).lower() == category.lower()]
    if warehouse: data = [r for r in data if _s(r.get("warehouse_name","")).lower() == warehouse.lower()]
    if min_qty:   data = [r for r in data if _f(r.get("quantity",0)) >= min_qty]

    result = []
    for r in sorted(data, key=lambda x: -_f(x.get("quantity",0))):
        sku = _s(_get(r, "sku_id"))
        info = cat.get(sku, {})
        result.append({
            "sku_id":             sku,
            "seller_article":     _s(r.get("seller_article")) or info.get("seller_article",""),
            "brand":              _s(r.get("brand")) or info.get("brand",""),
            "category":           _s(r.get("category")) or info.get("category",""),
            "product_name":       info.get("product_name",""),
            "warehouse_name":     _s(r.get("warehouse_name")),
            "quantity":           _f(r.get("quantity",0)),
            "total_stock":        _f(r.get("total_stock",0)),
            "in_transit_to_customer": _f(r.get("in_transit_to_customer",0)),
            "in_transit_returns": _f(r.get("in_transit_returns",0)),
            "cost_price":         info.get("cost_price", 0.0),
        })
    return result


@router.get("/stocks/summary")
async def stocks_summary(_=Depends(require_auth)):
    """Сводка по остаткам: total FBO + в пути + топ по кол-ву."""
    data = _load("warehouse_stocks")
    cat  = _get_catalog()

    by_sku: dict[str, dict] = {}
    for r in data:
        sku  = _s(_get(r,"sku_id"))
        if not sku: continue
        if sku not in by_sku:
            info = cat.get(sku, {})
            by_sku[sku] = {
                "sku_id":         sku,
                "seller_article": _s(r.get("seller_article")) or info.get("seller_article",""),
                "brand":          _s(r.get("brand")) or info.get("brand",""),
                "category":       _s(r.get("category")) or info.get("category",""),
                "product_name":   info.get("product_name",""),
                "total_fbo":      0.0,
                "in_transit_to_customer": 0.0,
                "in_transit_returns":     0.0,
                "cost_price":     info.get("cost_price",0.0),
            }
        by_sku[sku]["total_fbo"] += _f(r.get("quantity",0))
        by_sku[sku]["in_transit_to_customer"] += _f(r.get("in_transit_to_customer",0))
        by_sku[sku]["in_transit_returns"]     += _f(r.get("in_transit_returns",0))

    rows = sorted(by_sku.values(), key=lambda x: -x["total_fbo"])
    total_fbo     = sum(r["total_fbo"] for r in rows)
    total_transit = sum(r["in_transit_to_customer"] for r in rows)
    total_returns = sum(r["in_transit_returns"] for r in rows)
    total_cost    = sum(r["cost_price"]*r["total_fbo"] for r in rows)

    return {
        "total_skus":         len(rows),
        "total_fbo_stock":    round(total_fbo,0),
        "total_in_transit":   round(total_transit,0),
        "total_returns_transit": round(total_returns,0),
        "total_stock_value":  round(total_cost,2),
        "items":              rows[:200],
    }


@router.get("/ads")
async def ads(
    date_from:   Optional[str] = Query(None),
    date_to:     Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    _=Depends(require_auth),
):
    data = _filter_date_col(_load("ad_costs"), "charge_date", date_from, date_to)
    if campaign_id:
        data = [r for r in data if _s(r.get("campaign_id","")) == campaign_id]

    # Aggregate by campaign
    by_camp: dict[str, dict] = {}
    for r in data:
        cid = _s(r.get("campaign_id","")) or "—"
        if cid not in by_camp:
            by_camp[cid] = {
                "campaign_id":   cid,
                "campaign_name": _s(r.get("campaign_name")),
                "section":       _s(r.get("section")),
                "total_spent":   0.0,
                "records":       0,
                "first_date":    str(r.get("charge_date",""))[:10],
                "last_date":     str(r.get("charge_date",""))[:10],
            }
        by_camp[cid]["total_spent"] += _f(r.get("amount"))
        by_camp[cid]["records"]     += 1
        d = str(r.get("charge_date",""))[:10]
        if d < by_camp[cid]["first_date"]: by_camp[cid]["first_date"] = d
        if d > by_camp[cid]["last_date"]:  by_camp[cid]["last_date"]  = d

    total_spent = sum(r["total_spent"] for r in by_camp.values())
    rows = sorted(by_camp.values(), key=lambda x: -x["total_spent"])
    for r in rows: r["total_spent"] = round(r["total_spent"],2)

    # Raw records
    raw = [{
        "campaign_id":   _s(r.get("campaign_id")),
        "campaign_name": _s(r.get("campaign_name")),
        "charge_date":   str(r.get("charge_date",""))[:10],
        "amount":        round(_f(r.get("amount")),2),
        "section":       _s(r.get("section")),
    } for r in sorted(data, key=lambda x: str(x.get("charge_date","")))]

    return {
        "total_spent":      round(total_spent, 2),
        "campaigns_count":  len(by_camp),
        "by_campaign":      rows,
        "records":          raw,
    }


@router.get("/returns")
async def returns(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    brand:     Optional[str] = Query(None),
    _=Depends(require_auth),
):
    data = _filter_date_col(_load("returns"), "order_date", date_from, date_to)
    if brand:
        data = [r for r in data if _s(r.get("brand","")).lower() == brand.lower()]

    by_reason: dict[str,int] = {}
    by_brand:  dict[str,int] = {}
    for r in data:
        reason = _s(r.get("return_reason")) or "Не указана"
        brand_  = _s(r.get("brand")) or "—"
        by_reason[reason] = by_reason.get(reason,0) + 1
        by_brand[brand_]  = by_brand.get(brand_,0) + 1

    rows = [{
        "sku_id":        _s(r.get("sku_id")),
        "brand":         _s(r.get("brand")),
        "category":      _s(r.get("category")),
        "status":        _s(r.get("status")),
        "order_date":    str(r.get("order_date",""))[:10],
        "return_reason": _s(r.get("return_reason")),
        "pvz_address":   _s(r.get("pvz_address")),
    } for r in data]

    return {
        "total_returns": len(rows),
        "by_reason":     sorted([{"reason":k,"count":v} for k,v in by_reason.items()],key=lambda x:-x["count"]),
        "by_brand":      sorted([{"brand":k,"count":v} for k,v in by_brand.items()],key=lambda x:-x["count"])[:10],
        "records":       rows,
    }


@router.get("/supply-risk")
async def supply_risk(max_days: int = Query(30), _=Depends(require_auth)):
    data = _load("supply_recommendations")
    cat  = _get_catalog()
    rows = []
    for r in data:
        days  = _f(r.get("days_of_stock",999))
        level = _s(r.get("stock_level","")).lower()
        loss  = _f(r.get("potential_revenue_loss_28d",0))
        if days > max_days: continue
        sku  = _s(_get(r,"sku_id"))
        info = cat.get(sku, {})
        risk = "critical" if days<=7 or "критический" in level else \
               "warning"  if days<=14 or loss>50000 else "ok"
        rows.append({
            "sku_id":             sku,
            "seller_article":     _s(r.get("seller_article")) or info.get("seller_article",""),
            "product_name":       info.get("product_name",""),
            "region":             _s(r.get("region")),
            "avg_orders_per_day": round(_f(r.get("avg_orders_per_day")),2),
            "days_of_stock":      round(days,1),
            "stock_level":        _s(r.get("stock_level")),
            "revenue_loss_28d":   round(loss,2),
            "rec_supply_28d":     round(_f(r.get("rec_supply_28d")),0),
            "risk":               risk,
            "cost_price":         info.get("cost_price",0.0),
        })
    rows.sort(key=lambda x:({"critical":0,"warning":1,"ok":2}[x["risk"]],-x["revenue_loss_28d"]))
    return {
        "critical": sum(1 for r in rows if r["risk"]=="critical"),
        "warning":  sum(1 for r in rows if r["risk"]=="warning"),
        "total":    len(rows),
        "items":    rows,
    }


@router.get("/files")
async def files(_=Depends(require_auth)):
    if not _REG.exists(): return []
    try: reg = json.loads(_REG.read_bytes())
    except Exception: return []
    rows = []
    for k, v in reg.items():
        extra = v.get("extra") or {}
        rows.append({
            "filename":    _s(v.get("filename")),
            "report_type": _s(extra.get("report_type") or v.get("report_type")),
            "domain":      _s(extra.get("domain")),
            "db_table":    _s(extra.get("db_table")),
            "rows":        int(_f(v.get("row_count",0))),
            "status":      _s(v.get("status","unknown")),
            "period_from": _s(extra.get("period_from")),
            "period_to":   _s(extra.get("period_to")),
            "loaded_at":   _s(v.get("processed_at","")),
        })
    return sorted(rows, key=lambda x: x["loaded_at"], reverse=True)


@router.get("/unit-economics")
async def unit_economics(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    sku_id:    Optional[str] = Query(None),
    _=Depends(require_auth),
):
    """Юнит-экономика по SKU: маржа, себестоимость, ROI."""
    tx  = _filter_period(_load("transactions"), date_from, date_to)
    cat = _get_catalog()

    if sku_id:
        tx = [r for r in tx if _sku(r) == sku_id]

    by_sku: dict[str, dict] = {}
    for r in tx:
        sku  = _sku(r)
        if not sku: continue
        info = cat.get(sku, {})
        cp   = info.get("cost_price", 0.0) or 0.0
        q    = _qty(r)

        if sku not in by_sku:
            by_sku[sku] = {
                "sku_id":         sku,
                "seller_article": _s(_get(r,"seller_article")) or info.get("seller_article",""),
                "brand":          _s(_get(r,"brand")) or info.get("brand",""),
                "category":       _s(_get(r,"category")) or info.get("category",""),
                "product_name":   _s(_get(r,"product_name")) or info.get("product_name",""),
                "cost_price":     cp,
                "quantity":       0, "revenue":0.0,
                "commission":0.0, "logistics":0.0, "storage":0.0,
                "total_cost":0.0, "gross_profit":0.0, "unit_margin":0.0,
            }

        by_sku[sku]["quantity"]   += q
        by_sku[sku]["revenue"]    += _rev(r)
        by_sku[sku]["commission"] += _comm(r)
        by_sku[sku]["logistics"]  += _logi(r)
        by_sku[sku]["storage"]    += _stor(r)
        by_sku[sku]["total_cost"] += cp * q

    result = []
    for v in by_sku.values():
        gross  = v["revenue"] - v["commission"] - v["logistics"] - v["storage"]
        margin = gross - v["total_cost"]
        v["gross_profit"] = round(gross,  2)
        v["unit_margin"]  = round(margin, 2)
        v["margin_pct"]   = round(margin / v["revenue"] * 100, 2) if v["revenue"] > 0 else 0.0
        v["roi_pct"]      = round(margin / v["total_cost"] * 100, 2) if v["total_cost"] > 0 else 0.0
        v["avg_price"]    = round(v["revenue"] / v["quantity"], 2) if v["quantity"] > 0 else 0.0
        for k in ["revenue","commission","logistics","storage","total_cost"]:
            v[k] = round(v[k], 2)
        result.append(v)

    result.sort(key=lambda x: -x["revenue"])
    return result
