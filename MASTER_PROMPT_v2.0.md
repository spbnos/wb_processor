# WB Intelligent Data Platform — MASTER PROMPT v2.0
**Дата обновления: 2026-05-29**

## Текущее состояние системы

### Что реализовано и работает
| Модуль | Статус | Файлы |
|--------|--------|-------|
| CanonicalReportClassifier | ✅ 31/32 файлов (97%) | classification/canonical_report_registry.py |
| Domain Parsers (8 типов) | ✅ | parsers/domain/ |
| DomainParserFactory | ✅ | parsers/domain/domain_parser_factory.py |
| DomainLoader | ✅ | storage/domain_loader.py |
| SmartMapper (исправлен) | ✅ 70/82 AUTO | wb_platform/smart_mapping/ |
| wb_field_registry | ✅ 82 поля, 70 analytics | knowledge_base/registry/wb_field_registry.json |
| Analytics API | ✅ 7 endpoints | api/routes/analytics.py |
| Analytics Dashboard | ✅ | dashboard/src/pages/Analytics.tsx |
| Review Queue | ✅ с auto-apply | api/routes/review.py |
| Layout + KB status | ✅ | dashboard/src/components/Layout.tsx |

### 8 типов файлов WB
| report_id | Файл | Domain | DB Table |
|-----------|------|--------|----------|
| daily_detailed | Ежедневный детализированный | sales_intelligence | transactions |
| weekly_report | Еженедельный отчёт | finance_intelligence | weekly_reports |
| ad_cost_history | История затрат | advertising_intelligence | ad_costs |
| supply_recommendations | Рекомендации по поставкам | warehouse_intelligence | supply_recommendations |
| warehouse_stocks | Остатки на складе | warehouse_intelligence | warehouse_stocks |
| returns | Возвраты | returns_intelligence | returns |
| price_template | Шаблон цен и скидок | pricing_intelligence | price_templates |
| paid_storage | Платное хранение | finance_intelligence | paid_storage |

### Поток обработки файла
```
incoming/ → CanonicalReportClassifier (confidence ≥ 0.7)
              ↓ known type           ↓ unknown type
         DomainParserFactory      SmartMapper (fallback)
              ↓                        ↓
         DomainLoader             DataLoader (transactions)
              ↓                        ↓
         data/loaded/{table}.json    data/loaded/transactions.json
              ↓
         processed/
```

### Analytics API endpoints
- `GET /api/analytics/summary?date_from=&date_to=` — KPI сводка
- `GET /api/analytics/sales?group_by=sku|brand|category|date`
- `GET /api/analytics/finance`
- `GET /api/analytics/stocks?warehouse=&brand=`
- `GET /api/analytics/ads?date_from=&date_to=`
- `GET /api/analytics/returns`
- `GET /api/analytics/supply-risk?max_days=30`
- `GET /api/analytics/files` — история обработанных файлов

### Критическая задача (текущая)
**77 items pending в review_queue.json** — стале данные от старого SmartMapper
```powershell
venv\Scripts\python reset_and_reprocess.py
```
После этого все файлы из incoming/ обработаются через CanonicalReportClassifier
и SmartMapper с исправленным реестром (0 review items ожидается).

## Следующие фазы

### Фаза 5 — Docker + PostgreSQL (не реализована)
- docker-compose.yml со всеми сервисами
- SQLAlchemy models для всех 8 таблиц
- Alembic migrations
- DomainLoader.use_db=True

### Фаза 6 — WB API интеграция (не реализована)
- Подключение к WB OpenAPI (токен продавца)
- Авто-скачивание новых отчётов
- Webhook на новые загрузки

### Фаза 7 — ML Intelligence (модули готовы, не подключены)
- AnomalyDetector (IsolationForest) → подключить к транзакциям
- StockoutPredictor → подключить к warehouse_stocks + supply_recommendations
- FeatureStore → реализовать feature_pipeline.py

### Фаза 8 — WB Canonical Semantic Registry
На основе документа prompt.txt — полный онтологический реестр:
- wb_reports (все типы с версионированием схем)
- wb_fields (canonical fields с синонимами)
- semantic_relations (связи между полями)
- schema_versions (история изменений WB)
- Интеграция с Neo4j для графа зависимостей

## Архитектурные решения

### Дедупликация файлов
- По struct_hash (хэш набора колонок) в processed_files.json
- По _source_file в каждом {table}.json (заменяем данные файла целиком)

### Header row detection
- 0 для большинства отчётов
- 1 для "Возвраты" (merged header: строка 0 = группы "Товар"/"ПВЗ")
- CanonicalClassification.header_row передаётся в парсер

### Fallback стратегия
- confidence < 0.7 → SmartMapper fallback → transactions
- SmartMapper авто-применяет маппинг с порогом 0.85 (AUTO_APPLY)
- 0.60-0.84 → NEEDS_REVIEW queue → пользователь одобряет → apply_review_decisions()

## Файлы которые нельзя трогать без ревью
- wb_platform/smart_mapping/smart_mapper.py (сложная логика confidence)
- review_queue/queue_store.py (state machine статусов)
- api/deps.py (lru_cache синглтоны)
