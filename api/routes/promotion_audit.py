"""
api/routes/promotion_audit.py — оперативный аудит рекламных кампаний WB.

GET  /promotion-audit/run          — полный аудит РК за период (кампании,
                                      статистика по товарам, конверсии, категории)
GET  /promotion-audit/balance      — баланс рекламного кабинета
GET  /promotion-audit/categories   — категории WB, доступные для РК у продавца

Источник API: integrations/wb_api/promotion_audit_service.py (read-only,
никаких изменений ставок/кампаний). WB API ключ берётся из переменной
окружения WB_API_KEY (config/settings.py) — без ключа модуль возвращает
понятную ошибку, не падает с 500.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import require_auth
from config.settings import WB_API_KEY
from integrations.wb_api.promotion_audit_service import PromotionAuditService
from integrations.wb_api.promotion_client import WBPromotionAPIError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/promotion-audit", tags=["promotion-audit"])


def _get_service() -> PromotionAuditService:
    if not WB_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "WB_API_KEY не настроен. Добавьте ключ категории 'Продвижение' "
                "в переменную окружения WB_API_KEY и перезапустите сервер."
            ),
        )
    return PromotionAuditService(api_key=WB_API_KEY)


@router.get("/run")
async def run_promotion_audit(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD, по умолчанию 7 дней назад"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD, по умолчанию сегодня"),
    max_campaigns: int = Query(50, ge=1, le=200),
    _=Depends(require_auth),
):
    """Полный аудит: список РК + статистика по товарам + конверсии + категории."""
    service = _get_service()
    try:
        report = service.run_audit(date_from=date_from, date_to=date_to, max_campaigns=max_campaigns)
    except WBPromotionAPIError as e:
        raise HTTPException(status_code=502, detail=f"Ошибка WB Promotion API: {e}")

    return {
        "generated_at": report.generated_at,
        "date_from": report.date_from,
        "date_to": report.date_to,
        "balance": report.balance,
        "categories": report.categories,
        "campaigns": [
            {
                "advert_id": c.advert_id,
                "name": c.name,
                "type_code": c.type_code,
                "type_label": c.type_label,
                "status_code": c.status_code,
                "status_label": c.status_label,
                "payment_type": c.payment_type,
                "daily_budget": c.daily_budget,
                "start_time": c.start_time,
                "subjects": c.subjects,
                "nm_ids": c.nm_ids,
                "views": c.views,
                "clicks": c.clicks,
                "ctr": c.ctr,
                "cpc": c.cpc,
                "cr": c.cr,
                "atbs": c.atbs,
                "orders": c.orders,
                "shks": c.shks,
                "sum_spent": c.sum_spent,
                "sum_price": c.sum_price,
                "products": c.products,
                "stats_warning": c.stats_warning,
            }
            for c in report.campaigns
        ],
        "errors": report.errors,
    }


@router.get("/balance")
async def get_balance(_=Depends(require_auth)):
    """Баланс рекламного кабинета (включая промо-бонусы)."""
    service = _get_service()
    try:
        return service.client.get_balance()
    except WBPromotionAPIError as e:
        raise HTTPException(status_code=502, detail=f"Ошибка WB Promotion API: {e}")


@router.get("/categories")
async def get_categories(_=Depends(require_auth)):
    """Категории (предметы) WB, доступные продавцу для рекламных кампаний."""
    service = _get_service()
    try:
        return service.client.get_supplier_subjects()
    except WBPromotionAPIError as e:
        raise HTTPException(status_code=502, detail=f"Ошибка WB Promotion API: {e}")
