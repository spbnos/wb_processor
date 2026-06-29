# Почему не появился пункт меню — и как исправить надёжно

## Диагноз
Проверка git-репозитория показала: из прошлой выдачи на GitHub попал
**только** MASTER_PROMPT_v5.0.md. Все 16 файлов кода (PromotionAudit.tsx,
promotion_audit.py, integrations/ и точечные правки) **не были закоммичены**
— поэтому пункта меню физически нет на сервере.

## Файлы в этом архиве — те же, что уже подтверждены рабочими в прошлом ответе
(py_compile / tsc --noEmit / vite build — все проверки пройдены повторно,
ничего не изменилось в логике, только повторная выдача того, что не дошло).

## Новые файлы (положить как есть, путь сохранён)
- integrations/__init__.py
- integrations/wb_api/__init__.py
- integrations/wb_api/promotion_client.py
- integrations/wb_api/promotion_audit_service.py
- api/routes/promotion_audit.py
- src/pages/PromotionAudit.tsx
- dashboard/src/pages/PromotionAudit.tsx

## Точечно изменённые файлы (заменить целиком)

| Файл в архиве            | Куда положить                       |
|---------------------------|--------------------------------------|
| config_settings.py        | config/settings.py                   |
| api_main.py                | api/main.py                         |
| requirements.txt           | requirements.txt (корень)           |
| src_App.tsx                 | src/App.tsx                        |
| dashboard_src_App.tsx      | dashboard/src/App.tsx               |
| src_Layout.tsx              | src/components/Layout.tsx          |
| dashboard_src_Layout.tsx   | dashboard/src/components/Layout.tsx |
| src_client.ts               | src/api/client.ts                  |
| dashboard_src_client.ts    | dashboard/src/api/client.ts         |

## ⚠️ КРИТИЧНО: после копирования файлов — реально закоммитить

Распаковка архива на диск — это НЕ то же самое, что попадание файлов в
GitHub-репозиторий. Если работаешь через git, выполни явно:

```bash
git add integrations/ api/routes/promotion_audit.py \
        src/pages/PromotionAudit.tsx dashboard/src/pages/PromotionAudit.tsx \
        config/settings.py api/main.py requirements.txt \
        src/App.tsx dashboard/src/App.tsx \
        src/components/Layout.tsx dashboard/src/components/Layout.tsx \
        src/api/client.ts dashboard/src/api/client.ts

git status
# Убедись, что ВСЕ перечисленные файлы видны в "Changes to be committed"
# Если что-то не подсветилось зелёным — значит путь скопирован неверно

git commit -m "Add promotion audit module (campaigns, stats, conversions)"
git push
```

Если используешь веб-интерфейс GitHub ("Add file → Upload files") —
убедись, что загружаешь файлы **в правильные подпапки** (например,
PromotionAudit.tsx должен оказаться внутри src/pages/, а не в корне
репозитория) — GitHub веб-загрузка иногда кладёт файлы туда, куда открыта
текущая папка, а не туда, куда они должны лежать по логике приложения.

## Проверка после деплоя
1. `dashboard/`: `npm install && npm run build`
2. Перезапустить backend (чтобы подхватился новый роут в api/main.py)
3. Открыть дашборд — пункт "Аудит РК" должен появиться в левом меню
4. Если меню всё ещё без пункта — открой src/components/Layout.tsx (или
   dashboard/src/components/Layout.tsx) на сервере и проверь, есть ли там
   строка `label: 'Аудит РК'` — если нет, значит файл не заменился
