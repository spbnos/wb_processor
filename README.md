# Фикс: backend не стартовал (404 на Review, статус OFFLINE)

## Диагноз
Backend никогда стабильно не стартовал бы — модуль аудита РК тут ни при чём,
он просто оказался той точкой, на которую вы наткнулись при перезапуске.
Полная цепочка падения при импорте api/main.py, исправлена шаг за шагом:

1. `db/` — пакет никогда не существовал в git-истории. `mapping_repository.py`
   импортировал из него `Mapping` только как тайп-хинт (не реальная ORM).
   Создан `db/models.py` — алиас на уже существующий `MappingObj`.
2. `worker/` — тоже не в git-истории, но код уже содержал явный комментарий
   `# mock до Docker`. Восстановлен ровно тот mock-режим, который уже
   подразумевался (`enqueue`/`get_result`/`queue_lengths`).
3. `python-multipart`, `structlog`, `prometheus-client` — отсутствовали в
   requirements.txt, хотя нужны для UploadFile/логирования/метрик.

Никакая новая бизнес-логика не добавлена — только восстановлено то, что уже
подразумевалось существующим кодом и комментариями.

## Куда положить

| Файл в архиве        | Куда положить              |
|------------------------|------------------------------|
| db/__init__.py         | db/__init__.py               |
| db/models.py           | db/models.py                 |
| worker/__init__.py     | worker/__init__.py           |
| worker/queue_client.py | worker/queue_client.py       |
| worker/task_models.py  | worker/task_models.py        |
| requirements.txt       | requirements.txt (корень, заменить) |
| MASTER_PROMPT_v5.0.md  | wb_platform/MASTER_PROMPT_v5.0.md (заменить) |

## После деплоя

```bash
git add db/ worker/ requirements.txt wb_platform/MASTER_PROMPT_v5.0.md
git commit -m "Fix backend startup: missing db/worker stubs + requirements deps"
git push

pip install -r requirements.txt
# перезапустить backend (uvicorn api.main:app --reload --port 8000)
```

Проверено локально: `import api.main` проходит до конца без ошибок,
`GET /api/review` → 200, `GET /api/promotion-audit/balance` → 503 с понятным
текстом (без WB_API_KEY — это ожидаемо, не баг).

## Отдельно — не входит в этот фикс, но замечено
В корне репозитория остались лишние плоские файлы от предыдущего деплоя
(api_main.py, config_settings.py, src_App.tsx и т.п. — без подчёркивания
правильных путей). Они не мешают работе (реальные файлы по правильным путям
уже пропатчены корректно), но это мусор, который стоит убрать вручную при
случае: `git rm api_main.py config_settings.py src_App.tsx src_Layout.tsx
src_client.ts dashboard_src_App.tsx dashboard_src_Layout.tsx dashboard_src_client.ts`
