"""
integrations/wb_api/promotion_client.py — клиент WB Promotion API (Реклама).

Источник истины (проверено вручную, web_search по dev.wildberries.ru,
2026-06-24, см. wb_platform/MASTER_PROMPT_v5.0.md журнал находок Шага 1.5
и аудит рекламных кампаний):

  Базовый URL:  https://advert-api.wildberries.ru
  Авторизация:  заголовок  Authorization: <API_KEY>  (категория токена "Продвижение")

Используемые методы (только чтение, никаких изменений ставок/кампаний):

  GET  /adv/v1/promotion/count        — список РК, сгруппированных по типу/статусу
  GET  /adv/v1/promotion/adverts      — детальная информация по списку advertId
                                         (тип, статус, params[].subjectId/subjectName,
                                         params[].nms[], dailyBudget, paymentType, startTime)
  GET  /adv/v3/fullstats              — статистика по дням/площадкам/товарам
                                         (views, clicks, ctr, cpc, cr, atbs, orders,
                                          shks, sum, sum_price; вложенно nms[] по товарам)
  GET  /adv/v1/balance                — баланс счёта кампаний (balance, net, bonus, cashbacks[])
  GET  /adv/v1/supplier/subjects      — предметы (категории WB), доступные для РК:
                                         [{name, id, count}]
  GET  /adv/v1/upd                    — история затрат (списания)

ВАЖНО — подтверждённые ограничения и риски (см. MASTER_PROMPT_v5.0, Шаг 1.5):
  - rate-limit разный для каждого метода (см. _RATE_LIMITS ниже), нарушение → 429
  - /adv/v3/fullstats: документирован баг, при котором часть кампаний отдаёт нули
    по views/sum/clicks при том, что в личном кабинете данные корректны — клиент
    НЕ должен интерпретировать нулевые метрики как «нет рекламы», только как
    «WB вернул такие данные», разница должна быть видна пользователю.
  - С 23 октября кампании типов 8 (custom bid) объединены в тип 9 (Aukціон);
    тип 8 как самостоятельный больше не создаётся, но архивные кампании могут
    оставаться с этим типом в истории — клиент не должен падать на неизвестном type.
  - Это read-only аудит-модуль: здесь нет методов изменения ставок/кампаний.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_BASE_URL = "https://advert-api.wildberries.ru"

# Подтверждённые лимиты запросов по методам (см. дайджесты/доку, Шаг 1.5).
# Используются для троттлинга наших собственных вызовов, не для обхода лимитов WB.
_RATE_LIMITS: dict[str, float] = {
    "/adv/v1/promotion/count":   0.3,   # до 5 запросов/сек
    "/adv/v1/promotion/adverts": 0.3,
    "/adv/v3/fullstats":         1.0,   # эмпирически мягче на статистике, но не документировано точно
    "/adv/v1/balance":           1.0,
    "/adv/v1/supplier/subjects": 12.0,  # подтверждено: максимум 1 запрос в 12 секунд
    "/adv/v1/upd":               1.0,
}


class WBPromotionAPIError(Exception):
    """Ошибка обращения к WB Promotion API (HTTP-уровень или бизнес-ошибка WB)."""

    def __init__(self, message: str, status_code: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass
class WBPromotionClient:
    """
    Тонкий read-only клиент WB Promotion API.

    Намеренно НЕ содержит методов изменения ставок/кампаний/бюджета —
    это аудит-модуль, не модуль управления.
    """

    api_key: str
    timeout: float = 30.0
    _last_call: dict[str, float] = field(default_factory=dict, repr=False)

    def _throttle(self, path: str) -> None:
        min_interval = _RATE_LIMITS.get(path, 1.0)
        last = self._last_call.get(path, 0.0)
        elapsed = time.monotonic() - last
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_call[path] = time.monotonic()

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        try:
            import httpx
        except ImportError as e:
            raise WBPromotionAPIError(
                "Модуль httpx не установлен. Добавьте httpx>=0.27.0 в requirements.txt "
                "и выполните pip install httpx."
            ) from e

        self._throttle(path)
        url = f"{_BASE_URL}{path}"
        headers = {"Authorization": self.api_key}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=headers, params=params)
        except httpx.RequestError as e:
            raise WBPromotionAPIError(f"Сетевая ошибка при запросе {path}: {e}") from e

        if resp.status_code == 401:
            raise WBPromotionAPIError(
                "401 Unauthorized — проверьте API-ключ и что у токена подключена "
                "категория 'Продвижение' (Promotion)",
                status_code=401,
            )
        if resp.status_code == 429:
            raise WBPromotionAPIError(
                f"429 Too Many Requests на {path} — превышен лимит запросов WB",
                status_code=429,
            )
        if resp.status_code >= 400:
            raise WBPromotionAPIError(
                f"WB API вернул {resp.status_code} на {path}: {resp.text[:300]}",
                status_code=resp.status_code,
                payload=resp.text,
            )

        try:
            return resp.json()
        except Exception as e:
            raise WBPromotionAPIError(f"Не удалось разобрать JSON-ответ {path}: {e}") from e

    # ── Публичные read-only методы ──────────────────────────────────────────

    def get_campaigns_count(self) -> dict:
        """
        GET /adv/v1/promotion/count
        Список РК, сгруппированных по type/status, с count и advert_list[{advertId, changeTime}].
        """
        return self._get("/adv/v1/promotion/count")

    def get_campaigns_info(self, advert_ids: list[int]) -> list[dict]:
        """
        GET /adv/v1/promotion/adverts
        Детальная информация по конкретным кампаниям: advertId, type, status,
        dailyBudget, paymentType, startTime, params[].subjectId/subjectName/nms[].
        WB ограничивает размер пакета id за один вызов — батчинг на стороне
        вызывающего кода (см. PromotionAuditService).
        """
        result = self._get("/adv/v1/promotion/adverts", params={"id": advert_ids})
        return result if isinstance(result, list) else []

    def get_fullstats(
        self,
        advert_ids: list[int],
        date_from: str,
        date_to: str,
    ) -> list[dict]:
        """
        GET /adv/v3/fullstats
        Детальная статистика по дням/площадкам/товарам для списка кампаний.
        Поля верхнего уровня и days[]: views, clicks, ctr, cpc, cr, atbs,
        canceled, orders, shks, sum, sum_price. days[].apps[].nms[] — разбивка
        по товарам внутри кампании.
        """
        params = {"ids": advert_ids, "beginDate": date_from, "endDate": date_to}
        result = self._get("/adv/v3/fullstats", params=params)
        return result if isinstance(result, list) else []

    def get_balance(self) -> dict:
        """GET /adv/v1/balance — {balance, net, bonus, cashbacks: [{sum, percent, expiration_date}]}."""
        return self._get("/adv/v1/balance")

    def get_supplier_subjects(self) -> list[dict]:
        """
        GET /adv/v1/supplier/subjects
        Категории (предметы) WB, доступные продавцу для создания РК: [{name, id, count}].
        """
        result = self._get("/adv/v1/supplier/subjects")
        return result if isinstance(result, list) else []

    def get_cost_history(self, date_from: str, date_to: str) -> list[dict]:
        """GET /adv/v1/upd — история затрат (списаний) за период."""
        result = self._get("/adv/v1/upd", params={"from": date_from, "to": date_to})
        return result if isinstance(result, list) else []
