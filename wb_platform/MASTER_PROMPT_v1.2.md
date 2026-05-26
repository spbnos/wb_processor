# 🧠 WB INTELLIGENT DATA PLATFORM — MASTER PROMPT v1.0
> Этот документ — единая точка памяти проекта.
> Копируй ЦЕЛИКОМ в начало каждого нового чата.
> После каждого шага Claude ОБНОВЛЯЕТ этот документ и выгружает новую версию.

---

## 🎯 КОНЕЧНАЯ ЦЕЛЬ СИСТЕМЫ

**WB Intelligent Data Platform** — self-learning, ML-driven, fully dockerized платформа для обработки файлов Wildberries.

Ключевые свойства:
- **Zero manual input**: система САМА маппирует колонки через NLP + fuzzy matching + embeddings
- **Self-learning**: каждое решение улучшает следующее
- **ML-driven**: прогнозы аномалий, дрейф данных, авто-решения
- **Enterprise observability**: structured logs, metrics, tracing
- **Multi-container**: 8+ Docker сервисов
- **Internal SaaS**: React dashboard — Command Center, не "формочки"

---

## 📦 ФУНДАМЕНТ (ГОТОВО — Шаги 1-7)

Проект находится в `/wb_processor/`. Полный zip: `wb_processor_FULL.zip`

### Готовые модули:
| Модуль | Файл | Статус |
|--------|------|--------|
| DB Models | `db/models.py` | ✅ |
| DB Engine | `db/database.py` | ✅ |
| File Watcher | `watcher/file_watcher.py` | ✅ |
| File Classifier | `classification/file_classifier.py` | ✅ |
| Interactive Mapper | `mapping/interactive_mapper.py` | ✅ (будет заменён smart engine) |
| Mapping Storage | `mapping/mapping_storage.py` | ✅ |
| Mapping Repository | `mapping/mapping_repository.py` | ✅ |
| Parser Engine | `parsers/parser_engine.py` | ✅ |
| Normalizer | `normalizers/normalizer.py` | ✅ |
| Data Loader | `storage/data_loader.py` | ✅ |
| Error Handler | `storage/error_handler.py` | ✅ |
| Pipeline | `pipeline.py` | ✅ |
| CLI Manager | `cli/commands.py` | ✅ |
| Main entry | `main.py` | ✅ |

### Тесты: 128/128 ✅ (Фаза 0) + 54/54 ✅ (SmartMapper)

### ФАЗА 1 — Шаг 8 ЗАВЕРШЁН ✅
Новые модули в :
| Файл | Описание | Статус |
|------|----------|--------|
|  | 300+ алиасов RU/EN для 24 полей | ✅ |
|  | 6-уровневый matcher (exact→fuzzy→word) | ✅ |
|  | Авто-определение типов из sample | ✅ |
|  | Score 0-1, уровни AUTO/REVIEW/LOW | ✅ |
|  | JSON/DB хранилище решений | ✅ |
|  | Главный класс, zero manual input | ✅ |

**Confidence thresholds:**
-  → AUTO_APPLY (без подтверждения)
-  → NEEDS_REVIEW (в очередь UI)
-  → LOW_CONF (требует ручного ввода)

### DB таблицы (PostgreSQL):
- `files` — история обработанных файлов
- `mappings` — конфигурации форматов
- `mapping_fields` — поля маппингов
- `products` — товары/SKU
- `transactions` — продажи WB
- `stocks` — остатки склада

### Текущий pipeline (синхронный, CLI):
```
incoming/ → Watcher → Classifier → [Interactive Mapper] → Parser → Normalizer → DataLoader → PostgreSQL
```

### requirements.txt (текущий):
```
pandas==2.2.2
openpyxl==3.1.2
psycopg2-binary==2.9.9
SQLAlchemy==2.0.30
watchdog==4.0.1
click==8.1.7
rich==13.7.1
python-dotenv==1.0.1
chardet==5.2.0
```

---

## 🏗️ ЦЕЛЕВАЯ АРХИТЕКТУРА (10 сервисов)

```
┌─────────────────────────────────────────────────────────┐
│                    NGINX / API Gateway                   │
└──────────┬──────────────────────────┬───────────────────┘
           │                          │
    ┌──────▼──────┐            ┌──────▼──────┐
    │   FastAPI   │            │  React      │
    │   API :8000 │            │  Dashboard  │
    └──────┬──────┘            └─────────────┘
           │
    ┌──────▼──────────────────────────────────┐
    │              Redis Queue                │
    └──┬─────────────┬──────────────┬─────────┘
       │             │              │
┌──────▼───┐  ┌──────▼───┐  ┌──────▼──────┐
│Ingestion │  │  Worker  │  │ ML Service  │
│ Service  │  │ (pipeline│  │  :8001      │
│          │  │  + smart │  │             │
└──────────┘  │  mapping)│  └──────┬──────┘
              └──────────┘         │
                                   │ MLflow
┌──────────────────────────────────▼──────┐
│           PostgreSQL :5432               │
│  + Feature Store tables                 │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│  Monitoring: Prometheus + Grafana       │
└─────────────────────────────────────────┘
```

---

## 📋 ПОЛНЫЙ ПЛАН РЕАЛИЗАЦИИ

### ФАЗА 1: SMART MAPPING ENGINE (Чат 2)
**Цель**: заменить ручной Interactive Mapper на AI-driven автоматику

#### Шаг 8: `smart_mapping/` — ядро интеллекта
- `smart_mapping/column_matcher.py` — fuzzy matching (rapidfuzz), similarity score
- `smart_mapping/alias_dictionary.py` — 200+ алиасов RU/EN для всех WB полей
- `smart_mapping/type_detector.py` — автоопределение типов из sample данных
- `smart_mapping/confidence_scorer.py` — итоговый confidence 0.0-1.0
- `smart_mapping/smart_mapper.py` — главный класс, заменяет InteractiveMapper
- `smart_mapping/learning_store.py` — хранит решения, улучшает со временем
- Тесты: 40+ assertions, coverage >90%

**Логика решений:**
```
confidence >= 0.85 → авто-применить, логировать
confidence 0.60-0.84 → применить, пометить для review
confidence < 0.60 → показать UI для confirmation (не CLI форму!)
```

#### Шаг 9: Интеграция SmartMapper в Pipeline
- Заменить `InteractiveMapper` на `SmartMapper` в `pipeline.py`
- Добавить `review_queue` — очередь решений с низким confidence
- Тесты интеграции

---

### ФАЗА 2: ASYNC INFRASTRUCTURE (Чат 3)
**Цель**: async pipeline, Redis queue, FastAPI

#### Шаг 10: Redis + Async Worker
- `docker-compose.yml` (базовый: postgres + redis)
- `ingestion/file_ingestion_service.py` — async watchdog → Redis queue
- `worker/pipeline_worker.py` — async consumer из Redis
- `worker/task_models.py` — Pydantic задачи
- Тесты с mock Redis

#### Шаг 11: FastAPI — API сервис
- `api/main.py` — FastAPI app
- `api/routes/files.py` — CRUD файлов, статус обработки
- `api/routes/mappings.py` — CRUD маппингов
- `api/routes/stats.py` — агрегаты, статистика
- `api/routes/review.py` — endpoint для подтверждения low-confidence маппингов
- `api/auth.py` — JWT + API key auth
- `api/middleware.py` — structured logging, request tracing
- OpenAPI docs автоматом

---

### ФАЗА 3: ML СИСТЕМА (Чат 4)
**Цель**: Model Registry, Training Pipeline, Inference, Drift Detection

#### Шаг 12: Feature Store
- `feature_store/schema.py` — DB таблицы для фич
- `feature_store/aggregator.py` — временные ряды: продажи, остатки, выручка
- `feature_store/feature_pipeline.py` — расчёт фич из transactions/stocks
- Новые DB таблицы: `feature_sets`, `feature_values`, `feature_metadata`

#### Шаг 13: ML Service
- `ml/model_registry.py` — версии моделей, rollback
- `ml/training_pipeline.py` — обучение: аномалии продаж, прогноз остатков
- `ml/inference_service.py` — FastAPI сервис :8001
- `ml/drift_detector.py` — мониторинг деградации модели
- MLflow интеграция для трекинга экспериментов
- Модели: IsolationForest (аномалии), Prophet/ARIMA (прогноз)

---

### ФАЗА 4: OBSERVABILITY (Чат 5)
**Цель**: production-grade мониторинг

#### Шаг 14: Structured Logging + Metrics
- `core/logging.py` — structlog, JSON формат, request_id трекинг
- `core/metrics.py` — prometheus_client: latency, errors, queue depth
- `core/tracing.py` — OpenTelemetry spans
- `monitoring/prometheus.yml` — конфиг
- `monitoring/grafana/dashboards/` — 3 дашборда: pipeline, ML, business

#### Шаг 15: Data Validation Layer
- `core/schema_validator.py` — Great Expectations / Pydantic schemas
- `core/anomaly_detector.py` — statistical anomalies в incoming данных
- Интеграция в pipeline перед DataLoader

---

### ФАЗА 5: DOCKER PLATFORM (Чат 6)
**Цель**: полная dockerization, production-ready

#### Шаг 16: Docker Compose Full Stack
- `docker-compose.yml` — все 8 сервисов
- `docker-compose.dev.yml` — override для разработки
- `Dockerfile` для каждого сервиса (multi-stage builds)
- `devops/nginx.conf` — reverse proxy
- `devops/scripts/` — init, healthcheck, backup скрипты
- `.env.example` — все переменные

#### Шаг 17: CI/CD
- `.github/workflows/ci.yml` — lint + tests + build
- `.github/workflows/cd.yml` — staging + production deploy
- `devops/k8s/` — Kubernetes manifests (опционально)

---

### ФАЗА 6: REACT DASHBOARD (Чат 7)
**Цель**: Command Center UI

#### Шаг 18: Dashboard Foundation
- React + Vite + TypeScript + Tailwind
- `dashboard/src/pages/CommandCenter.tsx` — главная страница
- `dashboard/src/components/PipelineStatus.tsx` — live статус
- `dashboard/src/components/FileQueue.tsx` — очередь файлов

#### Шаг 19: Smart Mapping UI
- `dashboard/src/pages/MappingReview.tsx` — подтверждение low-confidence
- `dashboard/src/components/ConfidenceCard.tsx` — карточка с % уверенности
- `dashboard/src/components/ColumnMapper.tsx` — визуальный маппинг

#### Шаг 20: Analytics & ML
- `dashboard/src/pages/Analytics.tsx` — бизнес метрики
- `dashboard/src/pages/MLInsights.tsx` — ML прогнозы, аномалии
- Recharts для графиков, real-time через WebSocket

---

## 🗂️ ФИНАЛЬНАЯ СТРУКТУРА ПРОЕКТА

```
wb_platform/
├── api/                    # FastAPI сервис
│   ├── main.py
│   ├── routes/
│   ├── auth.py
│   └── middleware.py
├── ingestion/              # Async file ingestion
│   ├── file_ingestion_service.py
│   └── task_models.py
├── worker/                 # Async pipeline worker
│   ├── pipeline_worker.py
│   └── consumer.py
├── smart_mapping/          # ★ AI mapping engine
│   ├── column_matcher.py
│   ├── alias_dictionary.py
│   ├── type_detector.py
│   ├── confidence_scorer.py
│   ├── smart_mapper.py
│   └── learning_store.py
├── feature_store/          # Feature engineering
│   ├── schema.py
│   ├── aggregator.py
│   └── feature_pipeline.py
├── ml/                     # ML system
│   ├── model_registry.py
│   ├── training_pipeline.py
│   ├── inference_service.py
│   └── drift_detector.py
├── core/                   # Shared utilities
│   ├── logging.py
│   ├── metrics.py
│   ├── tracing.py
│   ├── schema_validator.py
│   └── anomaly_detector.py
├── monitoring/             # Prometheus + Grafana
│   ├── prometheus.yml
│   └── grafana/
├── dashboard/              # React Command Center
│   ├── src/
│   └── package.json
├── devops/                 # Docker + CI/CD
│   ├── nginx.conf
│   └── scripts/
├── tests/                  # Integration tests
├── docker-compose.yml
├── docker-compose.dev.yml
└── .github/workflows/
# + всё из wb_processor/ встраивается в worker/ и smart_mapping/
```

---

## 📊 PROJECT STATE

```
ФАЗА 0 (Фундамент):   ████████████████████ 100% ✅ (128 тестов)
ФАЗА 1 (Smart Mapping): ████████████████████ 100% ✅ Шаг 8 ✅ | Шаг 9 ✅
ФАЗА 2 (Async Infra):   ░░░░░░░░░░░░░░░░░░░░   0%
ФАЗА 3 (ML System):     ░░░░░░░░░░░░░░░░░░░░   0%
ФАЗА 4 (Observability): ░░░░░░░░░░░░░░░░░░░░   0%
ФАЗА 5 (Docker):        ░░░░░░░░░░░░░░░░░░░░   0%
ФАЗА 6 (Dashboard):     ░░░░░░░░░░░░░░░░░░░░   0%
```

**Общий прогресс: ~28% (Фазы 0+1 завершены — 205 тестов)**

---

## 🔧 ТЕХНИЧЕСКИЙ ДОЛГ / ИЗВЕСТНЫЕ ПРОБЛЕМЫ

1. `InteractiveMapper` — требует ручного ввода. Заменить на `SmartMapper` в Шаге 8
2. Pipeline синхронный — заменить на async в Шаге 10
3. Нет auth в API — добавить в Шаге 11
4. `datetime.utcnow()` deprecated в Python 3.12 — заменить на `datetime.now(UTC)` везде
5. `parsers/tests/test_parser_engine.py` — конфликт с `test_parser_normalizer.py`, убрать

---

## 📌 ИНСТРУКЦИЯ ДЛЯ НОВОГО ЧАТА

### Как начать новый чат:

1. Скопируй этот документ ЦЕЛИКОМ
2. Добавь: `"Продолжаем WB Platform. Текущий чат: [НОМЕР]. Начинаем с Шага [N]"`
3. Прикрепи zip архив с кодом (если нужен доступ к файлам)
4. Claude сверяется с PROJECT STATE и начинает с нужного шага

### Что Claude делает в каждом шаге:
- Пишет production-ready код
- Пишет тесты (coverage > 85%)
- Обновляет PROJECT STATE в этом документе
- Выгружает обновлённый MASTER_PROMPT.md с новым zip

### Формат первого сообщения в новом чате:
```
[ВСТАВИТЬ MASTER_PROMPT.md ЦЕЛИКОМ]

Продолжаем WB Intelligent Data Platform.
Текущий чат: 2
Начинаем ФАЗУ 1: Smart Mapping Engine (Шаг 8).
Поехали.
```

---

## 🧠 АРХИТЕКТУРНЫЕ РЕШЕНИЯ (зафиксированные)

| Решение | Обоснование |
|---------|-------------|
| rapidfuzz для fuzzy matching | Быстрее fuzzywuzzy, C расширения |
| Redis для очереди | Простота, persistence, pub/sub |
| FastAPI (не Django) | async-first, автодоки, современный |
| SQLAlchemy 2.0 async | Совместимость с существующим кодом |
| structlog | JSON логи, context vars, лучше stdlib |
| MLflow | Стандарт для model registry |
| Pydantic v2 | Валидация + сериализация |
| React + Vite | Быстрая сборка, современный стек |
| Multi-stage Dockerfile | Минимальный image size |
| GitHub Actions | Бесплатно, интегрировано |

---

## 💾 ДАННЫЕ / ФОРМАТЫ

### Категории файлов WB:
- `wb_report` — продажи, финансы, детализация, заказы, возвраты
- `ad` — рекламные кампании, статистика, ставки
- `external` — остатки, себестоимость, прайс-листы, пользовательские данные

### Стандартные target_fields (24 поля):
`sku, barcode, name, brand, category, date, quantity, price, cost_price, revenue, commission, logistics, net_profit, warehouse, region, campaign_id, ad_spend, impressions, clicks, ctr, cpc, reserved, in_transit, ignore`

### Alias dictionary (пример структуры):
```python
ALIASES = {
  "sku": ["артикул wb", "nmid", "артикул", "sku", "арт", "article"],
  "price": ["цена розн", "розничная цена", "цена продажи", "price", "retail price"],
  ...
}
```

---

## 🚀 КРИТЕРИИ ГОТОВНОСТИ (Definition of Done)

Система считается готовой когда:
- [ ] SmartMapper confidence > 90% на реальных WB файлах
- [ ] API latency p99 < 200ms
- [ ] Pipeline throughput > 1000 строк/сек
- [ ] ML anomaly detection F1 > 0.85
- [ ] Dashboard loads < 2s
- [ ] All services healthy в docker-compose up
- [ ] CI/CD green на main branch
- [ ] 0 ручных действий для известных форматов

---

*Версия документа: 1.2 | Последнее обновление: Чат 2 (Шаги 8-9: SmartMapper + Pipeline ✅ — 205 тестов)*
