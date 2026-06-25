# Аудит рекламных кампаний WB — куда класть файлы

## Новые файлы (создать как есть, путь сохранён)
- integrations/__init__.py
- integrations/wb_api/__init__.py
- integrations/wb_api/promotion_client.py
- integrations/wb_api/promotion_audit_service.py
- api/routes/promotion_audit.py
- src/pages/PromotionAudit.tsx
- dashboard/src/pages/PromotionAudit.tsx

## Точечно изменённые файлы (заменить целиком — в каждом изменено только 1–2 места,
## см. секцию "ВНЕПЛАНОВЫЙ МОДУЛЬ" в MASTER_PROMPT_v5.0.md для точного диффа)

| Файл в архиве              | Куда положить (заменить)              |
|-----------------------------|----------------------------------------|
| config_settings.py          | config/settings.py                     |
| api_main.py                 | api/main.py                            |
| requirements.txt            | requirements.txt (корень репо)         |
| src_App.tsx                 | src/App.tsx                            |
| dashboard_src_App.tsx       | dashboard/src/App.tsx                  |
| src_Layout.tsx              | src/components/Layout.tsx              |
| dashboard_src_Layout.tsx    | dashboard/src/components/Layout.tsx    |
| src_client.ts               | src/api/client.ts                      |
| dashboard_src_client.ts     | dashboard/src/api/client.ts            |

## Обновлённый промт
- MASTER_PROMPT_v5.0.md → положить в wb_platform/MASTER_PROMPT_v5.0.md (заменить)

## Перед запуском
1. `pip install -r requirements.txt` (добавлен httpx>=0.27.0)
2. Установить переменную окружения: `WB_API_KEY=<ключ категории "Продвижение">`
3. В dashboard/: `npm install && npm run build` (если ещё не делали)

## Проверено перед выдачей
- python3 -m py_compile на всех 5 .py файлов — без ошибок
- npx tsc --noEmit — подтверждено через git stash/stash pop, что НЕ добавлено
  новых ошибок типизации (5 ошибок, не связанных с этим модулем, существовали
  до правок — см. MASTER_PROMPT_v5.0.md)
- npx vite build — успешная сборка дашборда с новой вкладкой
