"""
api/routes/commissions.py

GET  /commissions/rates               — все ставки (фильтр по category/subject)
GET  /commissions/subject/{subject}   — ставки для конкретного предмета
GET  /commissions/categories          — список категорий
GET  /commissions/calculator          — юнит-экономика калькулятор
POST /commissions/calculator/compute  — расчёт с параметрами

GET  /commissions/deductions          — сводка удержаний WB из данных
GET  /commissions/ratings             — рейтинг карточек (актуальный + история)
GET  /commissions/ratings/history     — список доступных периодов
"""
from __future__ import annotations
import json, logging
from pathlib import Path
from typing import Optional, Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from api.auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/commissions", tags=["commissions"])

_DATA    = Path(__file__).resolve().parents[2] / "data"
_LOADED  = _DATA / "loaded"
_HISTORY = _DATA / "rating_history.json"
_COMM    = _DATA / "wb_commissions.json"

# WB FBO Logistics tariffs by volume (source: Оферта 2024-2025)
# Format: (max_volume_l, base_cost_rub)
_LOGISTICS_FBO = [
    (0.5,  60.0),
    (1.0,  80.0),
    (2.0,  100.0),
    (5.0,  150.0),
    (10.0, 220.0),
    (20.0, 320.0),
    (50.0, 500.0),
    (999,  750.0),
]

# FBS base cost
_LOGISTICS_FBS = [
    (0.5,  75.0),
    (1.0,  100.0),
    (2.0,  130.0),
    (5.0,  180.0),
    (10.0, 250.0),
    (999,  380.0),
]

# WB storage cost per unit/day by warehouse cluster (руб/л/день)
# Source: Оферта WB
_STORAGE_RATE_PER_L_DAY = {
    "Коледино":   0.07, "Казань":     0.07, "Краснодар":  0.07,
    "Тула":       0.07, "Электросталь":0.07, "Подольск":  0.07,
    "_default":   0.07,
}


def _load_json(path: Path) -> Any:
    if not path.exists(): return []
    try: return json.loads(path.read_bytes())
    except: return []

def _f(v) -> float:
    try:
        if v is None: return 0.0
        f = float(str(v).replace(",","."))
        return 0.0 if f != f else f
    except: return 0.0

def _s(v) -> str:
    s = str(v).strip() if v is not None else ""
    return "" if s in ("nan","None","NaT") else s

def _logistics_cost(volume_l: float, scheme: str = "fbo") -> float:
    table = _LOGISTICS_FBS if scheme == "fbs" else _LOGISTICS_FBO
    for max_vol, cost in table:
        if volume_l <= max_vol:
            return cost
    return table[-1][1]

def _get_commission_for_subject(subject: str) -> dict:
    """Get commission rates for a subject from loaded wb_commissions.json."""
    rates = _load_json(_COMM)
    if not rates: return {}
    subj_lower = subject.lower().strip()
    for r in rates:
        if _s(r.get("subject","")).lower() == subj_lower:
            return r
    return {}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/rates")
async def get_rates(
    category: Optional[str] = Query(None),
    subject:  Optional[str] = Query(None),
    limit:    int           = Query(200, le=1000),
    _=Depends(require_auth),
):
    """Базовые ставки ВВ% WB для всех предметов."""
    data = _load_json(_COMM)
    if not data:
        return {"error": "Таблица комиссий не загружена. Добавь commission.xlsx в incoming/ и нажми ЗАПУСТИТЬ.",
                "items": [], "total": 0}
    if category:
        data = [r for r in data if _s(r.get("category","")).lower() == category.lower()]
    if subject:
        q = subject.lower()
        data = [r for r in data if q in _s(r.get("subject","")).lower()]
    return {
        "total": len(data),
        "items": data[:limit],
        "meta": {
            "categories": len({_s(r.get("category")) for r in _load_json(_COMM)}),
            "subjects":   len(_load_json(_COMM)),
        }
    }


@router.get("/subject/{subject}")
async def get_subject_rates(subject: str, _=Depends(require_auth)):
    """Ставки для конкретного предмета WB."""
    r = _get_commission_for_subject(subject)
    if not r:
        return {"error": f"Предмет {subject!r} не найден", "subject": subject}
    return r


@router.get("/categories")
async def get_categories(_=Depends(require_auth)):
    """Список категорий WB с диапазоном ставок FBO."""
    data = _load_json(_COMM)
    cats: dict[str, dict] = {}
    for r in data:
        cat = _s(r.get("category","")) or "Без категории"
        if cat not in cats:
            cats[cat] = {"category": cat, "subjects_count": 0,
                         "fbo_min": 999, "fbo_max": 0, "fbo_avg_sum": 0}
        cats[cat]["subjects_count"] += 1
        fbo = _f(r.get("fbo_pct", 0))
        if fbo > 0:
            cats[cat]["fbo_min"] = min(cats[cat]["fbo_min"], fbo)
            cats[cat]["fbo_max"] = max(cats[cat]["fbo_max"], fbo)
            cats[cat]["fbo_avg_sum"] += fbo
    result = []
    for cat, v in cats.items():
        v["fbo_avg"] = round(v["fbo_avg_sum"] / v["subjects_count"], 2) if v["subjects_count"] else 0
        v["fbo_min"] = v["fbo_min"] if v["fbo_min"] < 999 else 0
        del v["fbo_avg_sum"]
        result.append(v)
    return sorted(result, key=lambda x: x["category"])


@router.get("/deductions")
async def get_deductions(_=Depends(require_auth)):
    """
    Сводка всех удержаний WB из фактических данных транзакций.
    Разбивка: комиссия, логистика, хранение, штрафы, платная приёмка.
    """
    tx   = _load_json(_LOADED / "transactions.json")
    wkly = _load_json(_LOADED / "weekly_reports.json")
    stor = _load_json(_LOADED / "paid_storage.json")

    def _rev(r):  return _f(r.get("seller_payment") or r.get("revenue"))
    def _comm(r): return abs(_f(r.get("wb_commission") or r.get("commission")))
    def _logi(r): return _f(r.get("delivery_cost") or r.get("logistics"))
    def _stor(r): return _f(r.get("storage_cost"))
    def _pens(r): return _f(r.get("total_penalties"))

    # From transactions
    total_rev  = sum(_rev(r)  for r in tx)
    total_comm = sum(_comm(r) for r in tx)
    total_logi = sum(_logi(r) for r in tx)
    total_stor = sum(_stor(r) for r in tx)
    total_pens = sum(_pens(r) for r in tx)

    # From weekly reports (additional deductions)
    wkly_acceptance = sum(_f(r.get("acceptance_cost"))  for r in wkly)
    wkly_loyalty    = sum(_f(r.get("loyalty_cost"))     for r in wkly)
    wkly_other      = sum(_f(r.get("other_deductions")) for r in wkly)
    wkly_total_pay  = sum(_f(r.get("total_payable"))    for r in wkly)

    total_deductions = total_comm + total_logi + total_stor + total_pens

    # Effective kvv% from transactions
    kvv_pcts = [_f(r.get("kvv_final_pct") or r.get("kvv_pct")) for r in tx
                if _f(r.get("kvv_final_pct") or r.get("kvv_pct")) > 0]
    avg_kvv = round(sum(kvv_pcts)/len(kvv_pcts), 2) if kvv_pcts else 0

    # Per-SKU breakdown for biggest deductions
    by_sku: dict[str, dict] = {}
    for r in tx:
        sku = _s(r.get("sku_id") or r.get("sku"))
        if not sku: continue
        if sku not in by_sku:
            by_sku[sku] = {
                "sku_id": sku,
                "brand": _s(r.get("brand")),
                "category": _s(r.get("category")),
                "revenue": 0.0, "commission": 0.0,
                "logistics": 0.0, "storage": 0.0, "penalties": 0.0,
            }
        by_sku[sku]["revenue"]    += _rev(r)
        by_sku[sku]["commission"] += _comm(r)
        by_sku[sku]["logistics"]  += _logi(r)
        by_sku[sku]["storage"]    += _stor(r)
        by_sku[sku]["penalties"]  += _pens(r)

    top_deductions = sorted(
        [{"sku_id": v["sku_id"], "brand": v["brand"], "category": v["category"],
          "total_deductions": round(v["commission"]+v["logistics"]+v["storage"]+v["penalties"],2),
          "commission": round(v["commission"],2), "logistics": round(v["logistics"],2),
          "storage": round(v["storage"],2), "penalties": round(v["penalties"],2),
          "deduction_rate_pct": round((v["commission"]+v["logistics"]) / v["revenue"]*100, 1) if v["revenue"]>0 else 0}
         for v in by_sku.values()],
        key=lambda x: -x["total_deductions"]
    )[:50]

    return {
        "summary": {
            "total_revenue":          round(total_rev,   2),
            "total_commission_wb":    round(total_comm,  2),
            "total_logistics":        round(total_logi,  2),
            "total_storage":          round(total_stor,  2),
            "total_penalties":        round(total_pens,  2),
            "total_deductions":       round(total_deductions, 2),
            "effective_deduction_pct":round(total_deductions/total_rev*100, 2) if total_rev>0 else 0,
            "avg_kvv_pct":            avg_kvv,
            "net_to_seller":          round(total_rev - total_deductions, 2),
        },
        "weekly_additional": {
            "acceptance_cost": round(wkly_acceptance, 2),
            "loyalty_program": round(wkly_loyalty,    2),
            "other":           round(wkly_other,      2),
            "total_payable":   round(wkly_total_pay,  2),
        },
        "deduction_breakdown": [
            {"type": "Вознаграждение WB (ВВ)",    "amount": round(total_comm, 2),
             "pct_of_revenue": round(total_comm/total_rev*100, 2) if total_rev>0 else 0},
            {"type": "Логистика (доставка)",       "amount": round(total_logi, 2),
             "pct_of_revenue": round(total_logi/total_rev*100, 2) if total_rev>0 else 0},
            {"type": "Хранение",                   "amount": round(total_stor, 2),
             "pct_of_revenue": round(total_stor/total_rev*100, 2) if total_rev>0 else 0},
            {"type": "Штрафы и корректировки",     "amount": round(total_pens, 2),
             "pct_of_revenue": round(total_pens/total_rev*100, 2) if total_rev>0 else 0},
            {"type": "Приёмка (из отчётов)",       "amount": round(wkly_acceptance, 2),
             "pct_of_revenue": round(wkly_acceptance/total_rev*100, 2) if total_rev>0 else 0},
        ],
        "top_by_deductions": top_deductions,
    }


class CalcInput(BaseModel):
    # Product
    subject:          str   = ""       # предмет (для lookup комиссии)
    category:         str   = ""
    price:            float = 0.0      # розничная цена
    cost_price:       float = 0.0      # себестоимость
    volume_l:         float = 0.5      # объём упаковки
    weight_kg:        float = 0.3      # вес

    # Scheme
    scheme:           str   = "fbo"    # "fbo" | "fbs"
    warehouse:        str   = "_default"

    # Economics
    buyout_pct:       float = 80.0     # % выкупа (0–100)
    localization_pct: float = 70.0     # % локализации заказов (0–100)
    drr_pct:          float = 0.0      # ДРР (доля рекламных расходов в %), 0 = нет рекламы

    # Manual override
    custom_kvv_pct:   float = 0.0      # если 0 — берём из таблицы комиссий


@router.post("/calculator/compute")
async def compute_unit_economics(inp: CalcInput, _=Depends(require_auth)):
    """
    Полный расчёт юнит-экономики с учётом:
    - ВВ% из таблицы комиссий (или вручную)
    - Логистики FBO/FBS по объёму
    - % выкупа (влияет на фактическую стоимость логистики на единицу продажи)
    - Локализации заказов (коэффициент логистики)
    - ДРР (доля рекламных расходов)
    - Хранения (ориентировочно)
    """
    # 1. Commission rate
    if inp.custom_kvv_pct > 0:
        kvv = inp.custom_kvv_pct
        kvv_source = "manual"
    else:
        rates = _get_commission_for_subject(inp.subject) if inp.subject else {}
        if inp.scheme == "fbs":
            kvv = _f(rates.get("fbs_wb_pct", 0)) or 15.0
        else:
            kvv = _f(rates.get("fbo_pct", 0)) or 15.0
        kvv_source = "wb_table" if rates else "default"

    # 2. Base logistics
    logi_base = _logistics_cost(inp.volume_l, inp.scheme)

    # 3. Localization coefficient (affects FBO logistics)
    # WB charges higher logistics for out-of-zone delivery
    # 100% localization → base rate; 50% → base * 1.2 (approx)
    loc_coeff = 1.0 + max(0, (100 - inp.localization_pct)) / 100 * 0.3
    logi_effective = logi_base * loc_coeff

    # 4. Returns logistics (buyout_pct affects avg logistics per sold unit)
    # Each return = additional logistics cost (return shipment)
    # Return logistics ≈ 50% of forward logistics
    return_rate = max(0, 1 - inp.buyout_pct / 100)
    logi_per_sale = logi_effective + (logi_effective * 0.5 * return_rate / max(inp.buyout_pct/100, 0.01))

    # 5. Storage cost estimate (based on volume, assume 30-day turnover)
    storage_rate = _STORAGE_RATE_PER_L_DAY.get(inp.warehouse, _STORAGE_RATE_PER_L_DAY["_default"])
    storage_estimate = inp.volume_l * storage_rate * 30  # 30 days avg

    # 6. WB payment to seller
    wb_payment = inp.price * (1 - kvv / 100)

    # 7. Advertising cost per unit
    ad_cost = inp.price * (inp.drr_pct / 100)

    # 8. Gross margin (without cost_price)
    gross = wb_payment - logi_per_sale - storage_estimate - ad_cost

    # 9. Net margin (with cost_price)
    net = gross - inp.cost_price

    # 10. Breakeven price
    if (1 - kvv / 100) > 0:
        breakeven_no_cost = (logi_per_sale + storage_estimate + ad_cost) / (1 - kvv / 100)
        breakeven_with_cost = (logi_per_sale + storage_estimate + ad_cost + inp.cost_price) / (1 - kvv / 100)
    else:
        breakeven_no_cost = breakeven_with_cost = 0

    # 11. ROI
    roi = round(net / inp.cost_price * 100, 2) if inp.cost_price > 0 else 0

    return {
        "input": inp.dict(),
        "commission": {
            "kvv_pct":  kvv,
            "source":   kvv_source,
            "amount":   round(inp.price * kvv / 100, 2),
            "wb_payment": round(wb_payment, 2),
        },
        "logistics": {
            "base":           round(logi_base, 2),
            "localization_coeff": round(loc_coeff, 3),
            "effective":      round(logi_effective, 2),
            "return_rate_pct":round(return_rate * 100, 1),
            "per_sale":       round(logi_per_sale, 2),
        },
        "storage_estimate":   round(storage_estimate, 2),
        "ad_cost":            round(ad_cost, 2),
        "cost_price":         inp.cost_price,
        "unit_economics": {
            "gross_margin":           round(gross, 2),
            "gross_margin_pct":       round(gross / inp.price * 100, 2) if inp.price > 0 else 0,
            "net_margin":             round(net, 2),
            "net_margin_pct":         round(net / inp.price * 100, 2) if inp.price > 0 else 0,
            "breakeven_no_cost":      round(breakeven_no_cost, 2),
            "breakeven_with_cost":    round(breakeven_with_cost, 2),
            "roi_pct":                roi,
            "is_profitable":          net > 0,
        },
        "cost_breakdown": [
            {"item":"Розничная цена",     "amount": round(inp.price, 2)},
            {"item":"Выручка продавца",   "amount": round(wb_payment, 2)},
            {"item":f"Комиссия WB ({kvv}%)", "amount": -round(inp.price*kvv/100, 2)},
            {"item":"Логистика (на продажу)","amount": -round(logi_per_sale, 2)},
            {"item":"Хранение (оценочно)", "amount": -round(storage_estimate, 2)},
            {"item":f"Реклама (ДРР {inp.drr_pct}%)", "amount": -round(ad_cost, 2)},
            {"item":"Себестоимость",       "amount": -round(inp.cost_price, 2)},
            {"item":"ИТОГО МАРЖА",         "amount": round(net, 2)},
        ],
    }


@router.get("/calculator")
async def get_calculator_defaults(
    subject: Optional[str] = Query(None),
    _=Depends(require_auth),
):
    """Получить дефолтные параметры для калькулятора (ставки по предмету)."""
    rates = _get_commission_for_subject(subject) if subject else {}
    return {
        "subject":       subject or "",
        "fbo_pct":       _f(rates.get("fbo_pct", 15.0)),
        "fbs_wb_pct":    _f(rates.get("fbs_wb_pct", 18.5)),
        "fbs_dbs_pct":   _f(rates.get("fbs_dbs_pct", 10.0)),
        "fbs_express_pct": _f(rates.get("fbs_express_pct", 3.0)),
        "subjects_count": len(_load_json(_COMM)),
        "has_commission_table": len(_load_json(_COMM)) > 0,
    }


@router.get("/ratings")
async def get_ratings(
    period: Optional[str] = Query(None, description="YYYY-MM-DD_YYYY-MM-DD или 'latest'"),
    brand:  Optional[str] = Query(None),
    sku_id: Optional[str] = Query(None),
    _=Depends(require_auth),
):
    """Рейтинг карточек: актуальный период или конкретный."""
    # ratings data is also in product_ratings.json
    data = _load_json(_LOADED / "product_ratings.json")
    if not data:
        return {"items": [], "period": "", "total": 0,
                "error": "Нет данных. Загрузи ZIP-файл с рейтингом в incoming/ и нажми ЗАПУСТИТЬ."}

    if brand:  data = [r for r in data if _s(r.get("brand","")).lower() == brand.lower()]
    if sku_id: data = [r for r in data if _s(r.get("sku_id","")) == sku_id]

    periods = sorted({r.get("period_from","") for r in data if r.get("period_from")})
    current_period = max(periods) if periods else ""

    return {
        "total":          len(data),
        "period_from":    data[0].get("period_from","") if data else "",
        "period_to":      data[0].get("period_to","") if data else "",
        "avg_card_rating": round(sum(_f(r.get("card_rating")) for r in data)/len(data),2) if data else 0,
        "avg_review_rating": round(sum(_f(r.get("review_rating")) for r in data)/len(data),2) if data else 0,
        "items": sorted(data, key=lambda x: -_f(x.get("card_rating",0)))[:500],
    }


@router.get("/ratings/history")
async def get_ratings_history(_=Depends(require_auth)):
    """Список доступных периодов с рейтингами (для выбора в UI)."""
    if not _HISTORY.exists():
        return {"periods": [], "total": 0}
    try:
        history = json.loads(_HISTORY.read_bytes())
    except Exception:
        return {"periods": [], "total": 0}
    periods = []
    for key, meta in history.items():
        periods.append({
            "period_key":  key,
            "period_from": meta.get("period_from",""),
            "period_to":   meta.get("period_to",""),
            "source_file": meta.get("source_file",""),
            "loaded_at":   meta.get("loaded_at",""),
            "rows":        meta.get("rows", 0),
        })
    return {
        "periods": sorted(periods, key=lambda x: x["period_from"], reverse=True),
        "total":   len(periods),
    }


@router.get("/ratings/period/{period_key}")
async def get_ratings_for_period(period_key: str, _=Depends(require_auth)):
    """Рейтинг за конкретный период из архива."""
    if not _HISTORY.exists():
        return {"error": "Архив пуст"}
    try:
        history = json.loads(_HISTORY.read_bytes())
    except Exception:
        return {"error": "Ошибка чтения архива"}
    snapshot = history.get(period_key)
    if not snapshot:
        return {"error": f"Период {period_key!r} не найден"}
    return {
        "period_from": snapshot["period_from"],
        "period_to":   snapshot["period_to"],
        "source_file": snapshot["source_file"],
        "rows":        snapshot["rows"],
        "items":       snapshot["records"],
    }
