# 🧠 WB INTELLIGENT DATA PLATFORM — MASTER PROMPT v3.0
> Обновлён: 2026-05-30. Единая точка памяти проекта.
> Копируй ЦЕЛИКОМ в начало каждого нового чата с Claude.

---

## 🎯 ГЛОБАЛЬНАЯ ЦЕЛЬ

**Unified Semantic Behavioral Intelligence Layer over Wildberries ecosystem.**

Не просто аналитика — это:
- **Canonical Semantic Registry** всех WB-сущностей (Palantir/Databricks уровень)
- **Self-learning ingestion** с историческим versioning схем
- **Unit Economics Engine** с формулами из Оферты
- **ML Intelligence**: stockout, аномалии, прогнозы маржи
- **Zero manual input**: AI маппинг + human-in-the-loop review

---

## ✅ РЕАЛИЗОВАНО (v2.0 → актуально)

### Инфраструктура
| Модуль | Путь | Статус |
|--------|------|--------|
| CanonicalReportClassifier | `classification/canonical_report_registry.py` | ✅ 8 типов, 97% coverage |
| DomainParserFactory | `parsers/domain/domain_parser_factory.py` | ✅ 8 парсеров |
| DomainLoader | `storage/domain_loader.py` | ✅ дедупликация по файлу |
| SmartMapper | `wb_platform/smart_mapping/smart_mapper.py` | ✅ 70/82 AUTO |
| KnowledgeBase | `knowledge_base/registry/wb_field_registry.json` | ✅ 82 поля, 643 термина |
| Analytics API | `api/routes/analytics.py` | ✅ 8 endpoints |
| Analytics Dashboard | `dashboard/src/pages/Analytics.tsx` | ✅ 6 вкладок |
| Review Queue | `api/routes/review.py` | ✅ auto-apply |
| ProcessedRegistry | `core/processed_registry.py` | ✅ extra={} поддержка |
| Process-All endpoint | `api/routes/files.py` | ✅ /process-all |

### Обработанные типы файлов (8/9)
| report_id | Файл WB | Domain | Table |
|-----------|---------|--------|-------|
| daily_detailed | Ежедневный детализированный | sales_intelligence | transactions |
| weekly_report | Еженедельный отчёт | finance_intelligence | weekly_reports |
| ad_cost_history | История затрат (реклама) | advertising_intelligence | ad_costs |
| supply_recommendations | Рекомендации по поставкам | warehouse_intelligence | supply_recommendations |
| warehouse_stocks | Остатки на складе (report_2026_*.xlsx) | warehouse_intelligence | warehouse_stocks |
| returns | Возвраты | returns_intelligence | returns |
| price_template | Шаблон цен | pricing_intelligence | price_templates |
| paid_storage | Платное хранение | finance_intelligence | paid_storage |
| **product_catalog** | **Актуальные_остатки_fixed.xlsx** | **product_intelligence** | **product_catalog** ← НУЖЕН |

### Текущие данные (после ЗАПУСТИТЬ от 2026-05-30)
- `transactions.json`: 4050 записей, 2026-05-03 → 2026-05-16 (смешанная схема old/new!)
- `warehouse_stocks.json`: 2884 записей (по складам, long format)
- `supply_recommendations.json`: 650 записей
- `ad_costs.json`: 47 записей
- `returns.json`: 423 записей
- `weekly_reports.json`: 191 записей (с 2024-07-15!)
- `price_templates.json`: 1413 записей

---

## 🚨 ИЗВЕСТНЫЕ БАГИ (требуют исправления)

### БАГ-1: Смешанная схема transactions.json
- 2604 old-schema записей: ключи `revenue, commission, logistics, date, transaction_type`
- 1446 new-schema записей: ключи `seller_payment, wb_commission, delivery_cost, sale_date`
- **Причина**: старые данные от DataLoader не были очищены перед деплоем новых парсеров
- **Фикс**: нормализовать analytics.py чтобы читать ОБЕ схемы + очистить при следующем reset

### БАГ-2: Период фильтр показывает данные неверно
- Транзакции: `sale_date` (новые) И `date` (старые) — analytics.py фильтрует только по `sale_date`
- Результат: 2604 записей с `date` но без `sale_date` игнорируются в фильтре
- **Фикс**: analytics.py должен fallback `sale_date` → `date` → `_period_from`

### БАГ-3: product_catalog не обрабатывается
- `Актуальные_остатки_fixed.xlsx` = КАТАЛОГ ТОВАРОВ (не складские остатки!)
- Содержит: `Цена закупочная` (себестоимость!), атрибуты товара, `Артикул (Код)` = WB nmID
- **Критично**: без себестоимости нет юнит-экономики
- **Фикс**: добавить 9-й тип `product_catalog` в реестр + парсер

### БАГ-4: Комиссия отображается как отрицательная (-4950₽)
- Old-schema `commission` хранится как положительное число (расход)
- New-schema `wb_commission` тоже положительное
- Analytics показывает `-4950₽` — double-sign bug
- **Фикс**: в analytics.py не нужно делать `-abs()` для commission

---

## 📐 ПЛАН МАСШТАБИРОВАНИЯ — ЭТАПЫ И ШАГИ

### ЭТАП 3 — Unit Economics & Data Quality (ТЕКУЩИЙ ПРИОРИТЕТ)
**Цель**: правильные цифры в Analytics, юнит-экономика на уровне SKU

#### Шаг 3.1 — Нормализация transactions (исправить БАГ-1 и БАГ-2)
- analytics.py: универсальный helper `_get_field(record, *aliases)` для обеих схем
- `sale_date` || `date` || `_period_from` для дат
- `seller_payment` || `revenue` для выручки
- `wb_commission` || `commission` для комиссии
- `delivery_cost` || `logistics` для логистики

#### Шаг 3.2 — Product Catalog Parser (исправить БАГ-3)
- Новый тип `product_catalog` в `canonical_report_registry.py`
- Новый `product_catalog_parser.py` в `parsers/domain/`
- Таблица `product_catalog.json`: sku_id, seller_article, barcode, cost_price, brand, category, attributes
- JOIN в analytics: transactions ← product_catalog по `sku_id`

#### Шаг 3.3 — Unit Economics Engine
- Формула из Оферты:
  ```
  unit_margin = seller_payment - cost_price - delivery_cost - storage_cost - paid_storage_share
  unit_margin_pct = unit_margin / retail_price * 100
  ```
- Analytics /summary: добавить `avg_unit_margin`, `avg_unit_margin_pct`
- Analytics /sales: добавить `cost_price`, `unit_margin`, `margin_pct` per SKU

#### Шаг 3.4 — Warehouse Intelligence Dashboard
- Вкладка Остатки: добавить "В пути до покупателей" + "Возвраты в пути"
- По кластерам (FBO склады — динамические колонки уже parsed)
- Дни остатка = total_stock / avg_orders_per_day

#### Шаг 3.5 — Рекламная вкладка (уже есть данные в ad_costs.json)
- Добавить в Analytics.tsx вкладку "Реклама" (уже есть но пустая)
- ROAS = revenue_from_sku / ad_spend_for_sku (нужен join с transactions по campaign → sku)
- CPO = ad_spend / orders_count

---

### ЭТАП 4 — Canonical Semantic Registry (по promт.txt)
**Цель**: enterprise ontology всех WB-сущностей

#### Шаг 4.1 — wb_canonical_registry.json
```json
{
  "version": "1.0",
  "reports": [{ "report_id": "daily_detailed", "official_name": "...", "domain": "...", "schema_versions": [...] }],
  "fields": [{ "field_id": "uuid", "canonical_name": "seller_payment", "wb_aliases": [...], "unit": "RUB" }],
  "metrics": [{ "metric_id": "unit_margin", "formula": "...", "dependencies": [...] }]
}
```

#### Шаг 4.2 — Schema Version Tracking
- При каждой загрузке файла: вычислять schema_hash по набору колонок
- Хранить в `data/schema_versions.json`
- Если schema_hash изменился → alert в UI + запрос в Review

#### Шаг 4.3 — WB Offer Intelligence (Оферта)
- Парсить PDF Оферты на комиссии, логистику, хранение по категориям
- Таблица `wb_offer_rates.json`: category → {kvv_base, logistics_coeff, storage_rate, irp_pct}
- Использовать в Unit Economics расчёте

---

### ЭТАП 5 — Historical Time-Series Storage
**Цель**: snapshots для трендов, ML-features

#### Шаг 5.1 — Ежедневные снапшоты
- При загрузке каждого файла сохранять агрегат по SKU+дата в `data/snapshots/`
- Поля: sku_id, date, stock, orders, revenue, position_est

#### Шаг 5.2 — Trending Analytics
- /analytics/trends?sku_id=X&metric=revenue&period=30d
- Графики динамики по дням

---

### ЭТАП 6 — ML Intelligence (модули готовы, не подключены)
**Цель**: actionable predictions

#### Шаг 6.1 — StockoutPredictor → подключить к pipeline
- Вход: `warehouse_stocks` + `supply_recommendations` + `transactions`
- Выход: risk_level, days_to_stockout, recommended_supply_qty
- Показывать в дашборде "Риск стокаута" с action button

#### Шаг 6.2 — AnomalyDetector
- Вход: `transactions` по дням
- Выход: аномальные дни (резкое падение/рост продаж)
- Alert в CommandCenter

#### Шаг 6.3 — PriceOptimizer
- Вход: `price_templates` + `transactions` + competitor data
- Выход: recommended price per SKU для максимизации margin

---

### ЭТАП 7 — Docker + PostgreSQL
**Цель**: production-ready deployment

#### Шаг 7.1 — SQLAlchemy models для всех 9 таблиц
#### Шаг 7.2 — docker-compose.yml: FastAPI + PostgreSQL + Redis + Nginx + Dashboard
#### Шаг 7.3 — Alembic migrations

---

### ЭТАП 8 — WB API Integration
**Цель**: автоматическая загрузка отчётов

- WB OpenAPI token (OAuth2)
- Auto-download: Воронка продаж, История остатков, Поисковые запросы
- Scheduler: hourly/daily/weekly per report type

---

## 🏗️ ТЕКУЩАЯ АРХИТЕКТУРА (работает)

```
incoming/*.xlsx
    ↓ CanonicalReportClassifier (8 типов, conf ≥ 0.7)
    ↓ DomainParserFactory (8 domain parsers)
    ↓ DomainLoader → data/loaded/{table}.json
    ↓ SmartMapper fallback (для unknown types)
    
data/loaded/ → FastAPI /api/analytics/* → React Dashboard
```

### API endpoints (работают)
- `GET /api/analytics/summary` — KPI за период
- `GET /api/analytics/sales?group_by=brand|category|sku|date` — продажи
- `GET /api/analytics/finance` — финансы (еженедельные)
- `GET /api/analytics/stocks` — остатки по складам
- `GET /api/analytics/ads` — расходы рекламы
- `GET /api/analytics/returns` — возвраты
- `GET /api/analytics/supply-risk?max_days=30` — риск стокаута
- `GET /api/analytics/files` — история обработки
- `POST /api/files/process-all` — обработать incoming/
- `GET /api/files/incoming` — список в incoming/

---

## ⚠️ ПРАВИЛА ДЛЯ CLAUDE

1. **Никогда не ломать существующий функционал** — только через добавления
2. **Проверять syntax** (`python3 -m py_compile`) перед деплоем
3. **Тестировать на реальных данных** из `incoming/`
4. **Обновлять этот MASTER_PROMPT** после каждого значимого изменения
5. **Сначала читать** `wb_platform/MASTER_PROMPT_v3.0.md` в начале каждого чата
6. **Следовать приоритетам**: БАГ-fix → Этап 3 → Этап 4 → ...

---

## 📊 МЕТРИКИ КАЧЕСТВА (цели)

| Метрика | Сейчас | Цель |
|---------|--------|------|
| Типов файлов обработано | 8/9 | 9/9 |
| Coverage транзакций | ~35% (смешанная схема) | 100% |
| Unit economics доступна | ❌ | ✅ |
| Период фильтр точность | ~60% | 100% |
| Схем WB задокументировано | 8 | 25+ |
| ML predictions active | 0 | 3 |
