"""
integrations/wb_api/promotion_audit_service.py — оперативный аудит РК.

Собирает воедино:
  1. Сами РК продавца (тип, статус, бюджет, дата старта) — /adv/v1/promotion/count + /adv/v1/promotion/adverts
  2. Статистику по товарам внутри каждой РК — /adv/v3/fullstats (вложенный nms[])
  3. Конверсии (CTR, CR, atbs→orders) — те же поля fullstats
  4. Категории WB (предметы), к которым относятся товары в РК — /adv/v1/supplier/subjects,
     сопоставленные с params[].subjectId/subjectName из get_campaigns_info

Кэширование (data/wb_api_cache/) — обязательно, т.к. часть методов лимитирована
жёстко (supplier/subjects — 1 запрос/12 сек, promotion/adverts — до 5/сек) и
повторный аудит в рамках одной сессии не должен заново дёргать WB на каждый клик.

Это read-only аудит, ничего не пишет обратно в WB.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from integrations.wb_api.promotion_client import WBPromotionAPIError, WBPromotionClient

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "wb_api_cache"
_CACHE_TTL_SECONDS = 300  # 5 минут — баланс между свежестью и rate-limit'ами WB

# Подтверждённые типы кампаний (см. MASTER_PROMPT_v5.0, Шаг 1.5 + breaking change
# от 23 октября: тип 8 объединён в тип 9, но архивные РК могут оставаться с type=8)
CAMPAIGN_TYPE_LABELS: dict[int, str] = {
    4: "Кампания (тип 4, устаревший)",
    6: "Поиск (устаревший)",
    8: "Автоматическая (архивная, объединена с типом 9)",
    9: "Аукцион",
}

CAMPAIGN_STATUS_LABELS: dict[int, str] = {
    -1: "Удаляется",
    4: "Готова к запуску",
    7: "Завершена",
    8: "Отказался",
    9: "Активна",
    11: "Приостановлена",
}


@dataclass
class CampaignAuditRow:
    """Единая строка аудита: одна РК со сводной статистикой."""

    advert_id: int
    name: str = ""
    type_code: int = 0
    type_label: str = ""
    status_code: int = 0
    status_label: str = ""
    payment_type: str = ""
    daily_budget: float = 0.0
    start_time: str = ""
    subjects: list[dict] = field(default_factory=list)  # [{subjectId, subjectName}]
    nm_ids: list[int] = field(default_factory=list)
    # Сводная статистика за выбранный период (из fullstats)
    views: int = 0
    clicks: int = 0
    ctr: float = 0.0
    cpc: float = 0.0
    cr: float = 0.0
    atbs: int = 0
    orders: int = 0
    shks: int = 0
    sum_spent: float = 0.0
    sum_price: float = 0.0
    products: list[dict] = field(default_factory=list)  # детальная статистика по товарам (nms[])
    stats_warning: str = ""  # непустое, если WB вернул подозрительные нулевые метрики


@dataclass
class PromotionAuditReport:
    generated_at: str
    date_from: str
    date_to: str
    balance: dict = field(default_factory=dict)
    categories: list[dict] = field(default_factory=list)  # supplier/subjects, обогащённые usage
    campaigns: list[CampaignAuditRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # частичные сбои отдельных вызовов, не блокируют отчёт


class PromotionAuditService:
    def __init__(self, api_key: str, use_cache: bool = True):
        self.client = WBPromotionClient(api_key=api_key)
        self.use_cache = use_cache
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ── Кэш ───────────────────────────────────────────────────────────────

    def _cache_path(self, key: str) -> Path:
        safe = key.replace("/", "_")
        return _CACHE_DIR / f"{safe}.json"

    def _cache_get(self, key: str) -> Optional[Any]:
        if not self.use_cache:
            return None
        p = self._cache_path(key)
        if not p.exists():
            return None
        try:
            payload = json.loads(p.read_text("utf-8"))
        except Exception:
            return None
        if time.time() - payload.get("_cached_at", 0) > _CACHE_TTL_SECONDS:
            return None
        return payload.get("data")

    def _cache_set(self, key: str, data: Any) -> None:
        if not self.use_cache:
            return
        p = self._cache_path(key)
        try:
            p.write_text(
                json.dumps({"_cached_at": time.time(), "data": data}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[promotion_audit] cache write failed for {key}: {e}")

    # ── Основной метод аудита ────────────────────────────────────────────

    def run_audit(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        max_campaigns: int = 50,
    ) -> PromotionAuditReport:
        """
        Полный аудит: РК + статистика по товарам + категории + конверсии.

        date_from/date_to: YYYY-MM-DD. По умолчанию — последние 7 дней
        (баланс между глубиной аудита и объёмом данных за один проход).
        """
        if not date_to:
            date_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not date_from:
            date_from = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        report = PromotionAuditReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            date_from=date_from,
            date_to=date_to,
        )

        # 1. Баланс
        try:
            cached = self._cache_get("balance")
            report.balance = cached if cached is not None else self.client.get_balance()
            if cached is None:
                self._cache_set("balance", report.balance)
        except WBPromotionAPIError as e:
            report.errors.append(f"Баланс: {e}")
            logger.warning(f"[promotion_audit] balance failed: {e}")

        # 2. Категории WB, доступные для РК
        try:
            cached = self._cache_get("supplier_subjects")
            report.categories = cached if cached is not None else self.client.get_supplier_subjects()
            if cached is None:
                self._cache_set("supplier_subjects", report.categories)
        except WBPromotionAPIError as e:
            report.errors.append(f"Категории WB: {e}")
            logger.warning(f"[promotion_audit] supplier_subjects failed: {e}")

        # 3. Список РК (сгруппированный по типу/статусу)
        advert_ids: list[int] = []
        try:
            count_resp = self.client.get_campaigns_count()
            for group in count_resp.get("adverts", []) or []:
                for item in group.get("advert_list", []) or []:
                    aid = item.get("advertId")
                    if aid is not None:
                        advert_ids.append(aid)
        except WBPromotionAPIError as e:
            report.errors.append(f"Список РК: {e}")
            logger.error(f"[promotion_audit] promotion/count failed: {e}")
            return report  # без списка РК продолжать аудит бессмысленно

        if not advert_ids:
            report.errors.append("У продавца не найдено ни одной рекламной кампании.")
            return report

        advert_ids = advert_ids[:max_campaigns]

        # 4. Детальная информация по РК (батчами, т.к. WB лимитирует размер пакета)
        campaigns_info: dict[int, dict] = {}
        batch_size = 50  # консервативный батч, точный лимит размера пакета не подтверждён документально
        for i in range(0, len(advert_ids), batch_size):
            batch = advert_ids[i : i + batch_size]
            try:
                infos = self.client.get_campaigns_info(batch)
                for info in infos:
                    aid = info.get("advertId")
                    if aid is not None:
                        campaigns_info[aid] = info
            except WBPromotionAPIError as e:
                report.errors.append(f"Информация о РК (батч {i}): {e}")
                logger.warning(f"[promotion_audit] adverts batch failed: {e}")

        # 5. Статистика fullstats — подтверждено: считается только для статусов
        #    автоматическая/аукцион (типы 8/9); запрашиваем для всех, WB сам
        #    отфильтрует нерелевантные без ошибки.
        stats_by_id: dict[int, dict] = {}
        try:
            stats_list = self.client.get_fullstats(advert_ids, date_from, date_to)
            for s in stats_list:
                aid = s.get("advertId")
                if aid is not None:
                    stats_by_id[aid] = s
        except WBPromotionAPIError as e:
            report.errors.append(f"Статистика fullstats: {e}")
            logger.warning(f"[promotion_audit] fullstats failed: {e}")

        # 6. Сборка строк аудита
        for aid in advert_ids:
            info = campaigns_info.get(aid, {})
            stat = stats_by_id.get(aid, {})

            type_code = info.get("type", 0)
            status_code = info.get("status", 0)

            subjects: list[dict] = []
            nm_ids: list[int] = []
            for p in info.get("params", []) or []:
                if p.get("subjectId") is not None:
                    subjects.append({
                        "subjectId": p.get("subjectId"),
                        "subjectName": p.get("subjectName", ""),
                    })
                for nm in p.get("nms", []) or []:
                    nm_id = nm.get("nm") if isinstance(nm, dict) else nm
                    if nm_id is not None:
                        nm_ids.append(nm_id)

            # Извлекаем сводные метрики и детальную разбивку по товарам из fullstats
            products: list[dict] = []
            for day in stat.get("days", []) or []:
                for app in day.get("apps", []) or []:
                    for nm_stat in app.get("nms", []) or []:
                        products.append({
                            "date": day.get("date", ""),
                            "appType": app.get("appType"),
                            "nmId": nm_stat.get("nmId"),
                            "name": nm_stat.get("name", ""),
                            "views": nm_stat.get("views", 0),
                            "clicks": nm_stat.get("clicks", 0),
                            "orders": nm_stat.get("orders", 0),
                            "shks": nm_stat.get("shks", 0),
                            "sum": nm_stat.get("sum", 0),
                            "sum_price": nm_stat.get("sum_price", 0),
                        })

            views = stat.get("views", 0) or 0
            clicks = stat.get("clicks", 0) or 0
            sum_spent = stat.get("sum", 0) or 0

            # Подтверждённый риск из MASTER_PROMPT_v5.0 (Шаг 1.5): известный баг
            # WB, когда fullstats отдаёт нули по активной кампании. Помечаем,
            # не скрываем — решение, что делать с этим, остаётся за пользователем.
            stats_warning = ""
            if status_code == 9 and views == 0 and clicks == 0 and sum_spent == 0 and aid in stats_by_id:
                stats_warning = (
                    "Кампания активна, но WB вернул нулевую статистику за период. "
                    "Это задокументированный баг WB API (см. форум разработчиков) — "
                    "проверьте данные в личном кабинете перед выводами."
                )

            row = CampaignAuditRow(
                advert_id=aid,
                name=info.get("name", f"РК #{aid}"),
                type_code=type_code,
                type_label=CAMPAIGN_TYPE_LABELS.get(type_code, f"Неизвестный тип ({type_code})"),
                status_code=status_code,
                status_label=CAMPAIGN_STATUS_LABELS.get(status_code, f"Неизвестный статус ({status_code})"),
                payment_type=info.get("paymentType", ""),
                daily_budget=info.get("dailyBudget", 0.0) or 0.0,
                start_time=info.get("startTime", ""),
                subjects=subjects,
                nm_ids=nm_ids,
                views=views,
                clicks=clicks,
                ctr=stat.get("ctr", 0.0) or 0.0,
                cpc=stat.get("cpc", 0.0) or 0.0,
                cr=stat.get("cr", 0.0) or 0.0,
                atbs=stat.get("atbs", 0) or 0,
                orders=stat.get("orders", 0) or 0,
                shks=stat.get("shks", 0) or 0,
                sum_spent=sum_spent,
                sum_price=stat.get("sum_price", 0.0) or 0.0,
                products=products,
                stats_warning=stats_warning,
            )
            report.campaigns.append(row)

        return report
