"""
api/routes/analytics.py — бизнес-аналитика для дашборда.
GET /analytics/summary, /sales, /finance, /stocks, /ads, /returns, /supply-risk, /files
"""
from __future__ import annotations
import json, logging
from pathlib import Path
from typing import Optional, Any
from fastapi import APIRouter, Depends, Query
from api.auth import require_auth
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])

_DATA  = Path(__file__).resolve().parents[2] / "data" / "loaded"
_REG   = Path(__file__).resolve().parents[2] / "data" / "processed_registry.json"

def _load(table: str) -> list[dict]:
    p = _DATA / f"{table}.json"
    if not p.exists(): return []
    try: return json.loads(p.read_bytes())
    except Exception: return []

def _fp(records, col, dfrom, dto):
    if not dfrom and not dto: return records
    out = []
    for r in records:
        val = str(r.get(col,"") or r.get("_period_from",""))[:10]
        if not val: out.append(r); continue
        if dfrom and val < dfrom: continue
        if dto   and val > dto:   continue
        out.append(r)
    return out

def _f(v) -> float:
    try:
        if v is None: return 0.0
        return float(v)
    except: return 0.0

def _s(v) -> str:
    if v is None: return ""
    s = str(v).strip()
    return "" if s in ("nan","None","NaT") else s

@router.get("/summary")
async def summary(date_from: Optional[str]=Query(None), date_to: Optional[str]=Query(None),
                  _=Depends(require_auth)):
    tx   = _fp(_load("transactions"),  "sale_date",    date_from, date_to)
    wkly = _fp(_load("weekly_reports"),"period_start", date_from, date_to)
    rev  = sum(_f(r.get("seller_payment") or r.get("wb_sale_price") or r.get("revenue")) for r in tx)
    comm = sum(_f(r.get("wb_commission") or r.get("commission")) for r in tx)
    logi = sum(_f(r.get("delivery_cost") or r.get("logistics")) for r in tx)
    stor = sum(_f(r.get("storage_cost")) for r in tx)
    pens = sum(_f(r.get("total_penalties")) for r in tx)
    qty  = sum(int(_f(r.get("quantity",0))) for r in tx)
    rets = sum(int(_f(r.get("return_count",0))) for r in tx)
    net  = rev - comm - logi - stor - pens
    if not tx and wkly:
        rev  = sum(_f(r.get("sales_amount"))    for r in wkly)
        logi = sum(_f(r.get("logistics_cost"))  for r in wkly)
        stor = sum(_f(r.get("storage_cost"))    for r in wkly)
        pens = sum(_f(r.get("total_penalties")) for r in wkly)
        net  = sum(_f(r.get("total_payable"))   for r in wkly)
    brand_rev: dict[str,float]={}
    cat_rev:   dict[str,float]={}
    for r in tx:
        b=_s(r.get("brand")) or "—"; c=_s(r.get("category")) or "—"
        v=_f(r.get("seller_payment") or r.get("wb_sale_price") or r.get("revenue"))
        brand_rev[b]=brand_rev.get(b,0.0)+v; cat_rev[c]=cat_rev.get(c,0.0)+v
    skus={_s(r.get("sku_id") or r.get("sku")) for r in tx if r.get("sku_id") or r.get("sku")}
    dates=[str(r.get("sale_date",""))[:10] for r in tx if r.get("sale_date")]
    loaded=[p.stem for p in _DATA.glob("*.json") if p.stat().st_size>100] if _DATA.exists() else []
    return {
        "period_from": min(dates) if dates else (date_from or ""),
        "period_to":   max(dates) if dates else (date_to   or ""),
        "total_revenue":    round(rev,2), "total_commission": round(comm,2),
        "total_logistics":  round(logi,2),"total_storage":    round(stor,2),
        "total_penalties":  round(pens,2),"net_profit":       round(net,2),
        "sales_count":      qty,          "returns_count":    rets,
        "unique_skus":      len(skus),
        "avg_margin_pct":   round(net/rev*100,2) if rev>0 else 0.0,
        "top_brands":    [{"brand":k,"revenue":round(v,2)} for k,v in sorted(brand_rev.items(),key=lambda x:-x[1])[:8]],
        "top_categories":[{"category":k,"revenue":round(v,2)} for k,v in sorted(cat_rev.items(),key=lambda x:-x[1])[:8]],
        "domains_loaded": loaded,
    }

@router.get("/sales")
async def sales(date_from: Optional[str]=Query(None), date_to: Optional[str]=Query(None),
                brand: Optional[str]=Query(None), category: Optional[str]=Query(None),
                sku_id: Optional[str]=Query(None), group_by: str=Query("brand"),
                limit: int=Query(100,le=500), _=Depends(require_auth)):
    tx = _fp(_load("transactions"),"sale_date",date_from,date_to)
    if brand:    tx=[r for r in tx if _s(r.get("brand","")).lower()==brand.lower()]
    if category: tx=[r for r in tx if _s(r.get("category","")).lower()==category.lower()]
    if sku_id:   tx=[r for r in tx if _s(r.get("sku_id","") or r.get("sku",""))==sku_id]
    agg: dict[str,dict]={}
    for r in tx:
        if group_by=="brand":      k=_s(r.get("brand")) or "—"
        elif group_by=="category": k=_s(r.get("category")) or "—"
        elif group_by=="date":     k=str(r.get("sale_date",""))[:10]
        else:                      k=_s(r.get("sku_id") or r.get("sku")) or "—"
        if k not in agg:
            agg[k]={"sku_id":_s(r.get("sku_id") or r.get("sku")),"seller_article":_s(r.get("seller_article")),
                    "brand":_s(r.get("brand")),"category":_s(r.get("category")),
                    "product_name":_s(r.get("product_name") or r.get("name")),
                    "quantity":0,"revenue":0.0,"commission":0.0,"logistics":0.0,"net_profit":0.0,"return_count":0}
        agg[k]["quantity"]    +=int(_f(r.get("quantity",0)))
        agg[k]["revenue"]     +=_f(r.get("seller_payment") or r.get("wb_sale_price") or r.get("revenue"))
        agg[k]["commission"]  +=_f(r.get("wb_commission") or r.get("commission"))
        agg[k]["logistics"]   +=_f(r.get("delivery_cost") or r.get("logistics"))
        agg[k]["return_count"]+=int(_f(r.get("return_count",0)))
    for v in agg.values():
        v["net_profit"]=round(v["revenue"]-v["commission"]-v["logistics"],2)
        v["revenue"]=round(v["revenue"],2); v["commission"]=round(v["commission"],2); v["logistics"]=round(v["logistics"],2)
    return sorted(agg.values(),key=lambda x:-x["revenue"])[:limit]

@router.get("/finance")
async def finance(date_from: Optional[str]=Query(None), date_to: Optional[str]=Query(None),
                  _=Depends(require_auth)):
    data=_fp(_load("weekly_reports"),"period_start",date_from,date_to)
    return [{"report_number":_s(r.get("report_number")),"period_start":str(r.get("period_start",""))[:10],
             "period_end":str(r.get("period_end",""))[:10],"sales_amount":round(_f(r.get("sales_amount")),2),
             "seller_payment":round(_f(r.get("seller_payment")),2),"logistics_cost":round(_f(r.get("logistics_cost")),2),
             "storage_cost":round(_f(r.get("storage_cost")),2),"total_penalties":round(_f(r.get("total_penalties")),2),
             "total_payable":round(_f(r.get("total_payable")),2)} for r in sorted(data,key=lambda x:str(x.get("period_start","")))]

@router.get("/stocks")
async def stocks(brand: Optional[str]=Query(None), category: Optional[str]=Query(None),
                 warehouse: Optional[str]=Query(None), min_qty: float=Query(0),
                 _=Depends(require_auth)):
    data=_load("warehouse_stocks")
    if brand:     data=[r for r in data if _s(r.get("brand","")).lower()==brand.lower()]
    if category:  data=[r for r in data if _s(r.get("category","")).lower()==category.lower()]
    if warehouse: data=[r for r in data if _s(r.get("warehouse_name","")).lower()==warehouse.lower()]
    if min_qty:   data=[r for r in data if _f(r.get("quantity",0))>=min_qty]
    return [{"sku_id":_s(r.get("sku_id")),"seller_article":_s(r.get("seller_article")),
             "brand":_s(r.get("brand")),"category":_s(r.get("category")),
             "warehouse_name":_s(r.get("warehouse_name")),"quantity":_f(r.get("quantity",0)),
             "total_stock":_f(r.get("total_stock",0))} for r in sorted(data,key=lambda x:-_f(x.get("quantity",0)))]

@router.get("/ads")
async def ads(date_from: Optional[str]=Query(None), date_to: Optional[str]=Query(None),
              campaign_id: Optional[str]=Query(None), _=Depends(require_auth)):
    data=_fp(_load("ad_costs"),"charge_date",date_from,date_to)
    if campaign_id: data=[r for r in data if _s(r.get("campaign_id",""))==campaign_id]
    return [{"campaign_id":_s(r.get("campaign_id")),"campaign_name":_s(r.get("campaign_name")),
             "charge_date":str(r.get("charge_date",""))[:10],"amount":round(_f(r.get("amount")),2),
             "section":_s(r.get("section"))} for r in sorted(data,key=lambda x:str(x.get("charge_date","")))]

@router.get("/returns")
async def returns(date_from: Optional[str]=Query(None), date_to: Optional[str]=Query(None),
                  brand: Optional[str]=Query(None), _=Depends(require_auth)):
    data=_fp(_load("returns"),"order_date",date_from,date_to)
    if brand: data=[r for r in data if _s(r.get("brand","")).lower()==brand.lower()]
    return [{"sku_id":_s(r.get("sku_id")),"brand":_s(r.get("brand")),"category":_s(r.get("category")),
             "status":_s(r.get("status")),"order_date":str(r.get("order_date",""))[:10],
             "return_reason":_s(r.get("return_reason"))} for r in data]

@router.get("/supply-risk")
async def supply_risk(max_days: int=Query(30), _=Depends(require_auth)):
    data=_load("supply_recommendations")
    rows=[]
    for r in data:
        days=_f(r.get("days_of_stock",999)); level=_s(r.get("stock_level","")).lower()
        loss=_f(r.get("potential_revenue_loss_28d",0))
        if days>max_days: continue
        risk="critical" if days<=7 or "критический" in level else "warning" if days<=14 or loss>50000 else "ok"
        rows.append({"sku_id":_s(r.get("sku_id")),"seller_article":_s(r.get("seller_article")),
                     "region":_s(r.get("region")),"avg_orders_per_day":round(_f(r.get("avg_orders_per_day")),2),
                     "days_of_stock":round(days,1),"stock_level":_s(r.get("stock_level")),
                     "revenue_loss_28d":round(loss,2),"rec_supply_28d":round(_f(r.get("rec_supply_28d")),0),"risk":risk})
    rows.sort(key=lambda x:({"critical":0,"warning":1,"ok":2}[x["risk"]],-x["revenue_loss_28d"]))
    return {"critical":sum(1 for r in rows if r["risk"]=="critical"),
            "warning":sum(1 for r in rows if r["risk"]=="warning"),
            "total":len(rows),"items":rows}

@router.get("/files")
async def files(_=Depends(require_auth)):
    if not _REG.exists(): return []
    try: reg=json.loads(_REG.read_bytes())
    except Exception: return []
    return [{"filename":_s(v.get("filename")),"report_type":_s((v.get("extra") or {}).get("report_type") or v.get("report_type")),
             "domain":_s((v.get("extra") or {}).get("domain")),"db_table":_s((v.get("extra") or {}).get("db_table")),
             "rows":int(_f(v.get("row_count",0))),"status":_s(v.get("status","unknown")),
             "period_from":_s((v.get("extra") or {}).get("period_from")),"period_to":_s((v.get("extra") or {}).get("period_to")),
             "loaded_at":_s(v.get("processed_at",""))} for k,v in reg.items()]
