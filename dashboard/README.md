# WB Platform — Command Center Dashboard

React + Vite + TypeScript dashboard для WB Intelligent Data Platform.

## Стек

- **React 18** + **TypeScript**
- **Vite** — сборка и dev server с proxy на API
- **Recharts** — интерактивные графики
- **Lucide React** — иконки
- **React Router v6** — навигация

## Страницы

| Путь | Страница | Описание |
|------|----------|----------|
| `/` | Command Center | Система, drop-zone для файлов |
| `/review` | Mapping Review | Подтверждение low-confidence маппингов |
| `/mappings` | Mappings | CRUD маппингов форматов |
| `/ml` | ML Insights | Модели, обучение, метрики |
| `/analytics` | Analytics | Графики: категории, очереди, review |

## Design System

Dark industrial / control room aesthetic:
- Палитра: `--bg-void`, `--bg-base`, `--bg-panel` → тёмные слои
- Акцент: `--amber` (#f59e0b) — активные элементы
- Статусы: `--green` / `--red` / `--amber`
- Типографика: Syne (заголовки), DM Mono (данные), Inter (текст)

## Запуск разработки

```bash
cd dashboard
npm install
npm run dev      # → http://localhost:5173

# API должен быть доступен на :8000 (proxy в vite.config.ts)
```

## Production build

```bash
npm run build    # → dist/
# Файлы из dist/ раздаёт nginx (см. devops/nginx.conf)
```

## Архитектура

```
src/
├── api/client.ts        — все API вызовы через fetch
├── components/          — переиспользуемые компоненты
│   ├── Badge.tsx        — статус бейджи
│   ├── ConfidenceBar.tsx — прогресс-бар confidence
│   ├── Layout.tsx       — sidebar + outlet
│   ├── Spinner.tsx      — индикатор загрузки
│   └── StatCard.tsx     — карточка метрики
├── hooks/useApi.ts      — useApi + usePolling хуки
├── pages/               — страницы роутера
├── types/index.ts       — TypeScript типы API
└── utils/format.ts      — форматирование чисел/дат
```

## Polling

Dashboard автоматически обновляет данные:
- `CommandCenter` — каждые 8 секунд
- `Health` — каждые 10 секунд
- Остальные страницы — при монтировании + ручной refresh
