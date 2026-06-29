# Найдена причина: requirements.txt лишился 3 строк

## Диагноз (через git pull, не угадано)
Между предыдущим ответом и этим кто-то закоммитил requirements.txt без
3 строк, которые я добавлял для фикса backend (python-multipart, structlog,
prometheus-client). Сам код (core/logging.py, core/metrics.py) их всё ещё
требует жёстко — значит backend падает ровно на том же месте, что раньше,
просто причина теперь "пакет не установлен", а не "модуль не существует".

## Фикс
requirements.txt — точечно восстановлены 3 строки. Никакой код не менялся.

## Куда положить
requirements.txt → requirements.txt (корень репозитория, заменить)
MASTER_PROMPT_v5.0.md → wb_platform/MASTER_PROMPT_v5.0.md (заменить)

## Что сделать после
```
pip install -r requirements.txt
```
Затем перезапустить backend (закрыть окно WB-API, если оно открыто,
запустить WB_PLATFORM.bat снова).

## Новый способ проверки — надёжнее, чем /api/stats/health
Открой в браузере: http://127.0.0.1:8000/docs

- Открылся Swagger UI со списком эндпоинтов → backend жив и это актуальный
  код. Проверь там, есть ли /api/promotion-audit/run в списке.
- Снова {"detail":"Not Found"} даже на /docs → порт 8000 занят чем-то
  посторонним, не нашим FastAPI. Выполни в cmd:
  netstat -ano | findstr :8000
  и посмотри, какой процесс (PID) слушает порт.
- Страница вообще не открывается (не 404, а "не удаётся подключиться") →
  backend-процесс не запущен физически, нужно смотреть окно WB-API.
