"""
CLI Manager — управление маппингами через терминал.

Команды:
    python main.py mappings list
    python main.py mappings show <id>
    python main.py mappings edit <id>
    python main.py mappings delete <id>
    python main.py mappings export [path]
    python main.py mappings import <path>

    python main.py run            ← запустить watcher
    python main.py scan           ← обработать существующие файлы
    python main.py status         ← статус системы
"""
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mapping.mapping_storage import MappingStorage
from mapping.mapping_repository import MappingRepository
from mapping.constants import CATEGORIES, SUBCATEGORIES, PURPOSES, TARGET_FIELDS, DATA_TYPES, DATE_FORMATS
from mapping.interactive_mapper import FieldMapping

console = Console()

# ─────────────────────────────────────────────────────────
# Storage singleton (JSON по умолчанию, меняется через --db)
# ─────────────────────────────────────────────────────────
def _get_storage(use_db: bool = False) -> MappingStorage:
    import mapping.mapping_storage as ms_mod
    return MappingStorage(use_db=use_db, json_path=ms_mod._DEFAULT_JSON_PATH)


# ─────────────────────────────────────────────────────────
# Группа: mappings
# ─────────────────────────────────────────────────────────
@click.group()
def cli():
    """WB File Processor — управление системой."""
    pass


@cli.group()
def mappings():
    """Управление маппингами форматов файлов."""
    pass


# ── list ─────────────────────────────────────────────────
@mappings.command("list")
@click.option("--db", is_flag=True, default=False, help="Использовать PostgreSQL")
@click.option("--all", "show_all", is_flag=True, default=False, help="Показать все включая удалённые")
@click.option("--category", "-c", default=None, help="Фильтр по категории")
def mappings_list(db: bool, show_all: bool, category: str):
    """Показать все маппинги."""
    storage = _get_storage(db)
    repo = MappingRepository(storage)
    items = repo.summary_list()

    if not show_all:
        items = [i for i in items if i["active"]]
    if category:
        items = [i for i in items if i["category"] == category]

    if not items:
        console.print("[dim]Маппингов не найдено.[/]")
        return

    table = Table(
        title=f"📋 Маппинги ({len(items)} шт.)",
        box=box.ROUNDED, header_style="bold cyan", show_lines=True,
    )
    table.add_column("ID",          style="bold yellow", width=5)
    table.add_column("Название",    style="white",       width=30)
    table.add_column("Категория",   style="cyan",        width=14)
    table.add_column("Подкатегория",style="dim",         width=14)
    table.add_column("Колонок",     style="green",       width=8)
    table.add_column("Hash",        style="dim",         width=18)
    table.add_column("Активен",     style="magenta",     width=8)

    for m in items:
        active = "✅" if m["active"] else "❌"
        table.add_row(
            str(m["id"]), m["name"], m["category"],
            m["subcategory"], str(m["columns"]),
            m["struct_hash"][:14] + "...", active,
        )

    console.print(table)
    stats = repo.stats()
    console.print(
        f"\n  Всего: [bold]{stats['total']}[/]  "
        f"Активных: [green]{stats['active']}[/]  "
        f"Удалённых: [dim]{stats['inactive']}[/]"
    )


# ── show ─────────────────────────────────────────────────
@mappings.command("show")
@click.argument("mapping_id", type=int)
@click.option("--db", is_flag=True, default=False)
def mappings_show(mapping_id: int, db: bool):
    """Показать детали маппинга по ID."""
    storage = _get_storage(db)
    m = storage.get_by_id(mapping_id)

    if not m:
        console.print(f"[red]Маппинг id={mapping_id} не найден.[/]")
        raise SystemExit(1)

    console.print(Panel(
        f"[bold cyan]Название:[/]    {m.name}\n"
        f"[bold cyan]Категория:[/]   {m.category} / {m.subcategory or '—'}\n"
        f"[bold cyan]Назначение:[/]  {m.purpose or '—'}\n"
        f"[bold cyan]Hash:[/]        {m.struct_hash}\n"
        f"[bold cyan]Колонок:[/]     {m.column_count or len(m.fields)}\n"
        f"[bold cyan]Активен:[/]     {'✅' if m.is_active else '❌'}\n"
        f"[bold cyan]Заметки:[/]     {m.notes or '—'}",
        title=f"[bold]Маппинг #{mapping_id}[/]",
        box=box.ROUNDED,
    ))

    if m.fields:
        table = Table(title="Поля", box=box.SIMPLE_HEAD, header_style="bold white")
        table.add_column("Колонка в файле", style="white")
        table.add_column("→ Поле",          style="green")
        table.add_column("Тип",             style="yellow")
        table.add_column("Формат даты",     style="dim")
        table.add_column("Обязательная",    style="magenta")

        for f in m.fields:
            req = "✅" if f.is_required else ""
            tgt = "[dim]— пропустить —[/]" if f.target_field == "ignore" else f.target_field
            table.add_row(
                f.source_column, tgt, f.data_type,
                f.date_format or "", req,
            )
        console.print(table)


# ── edit ─────────────────────────────────────────────────
@mappings.command("edit")
@click.argument("mapping_id", type=int)
@click.option("--db", is_flag=True, default=False)
def mappings_edit(mapping_id: int, db: bool):
    """Редактировать маппинг интерактивно."""
    storage = _get_storage(db)
    m = storage.get_by_id(mapping_id)

    if not m:
        console.print(f"[red]Маппинг id={mapping_id} не найден.[/]")
        raise SystemExit(1)

    console.print(Panel(
        f"Редактирование: [bold cyan]{m.name}[/] (id={mapping_id})",
        box=box.ROUNDED,
    ))

    updates = {}

    # Имя
    new_name = Prompt.ask("Новое название", default=m.name)
    if new_name != m.name:
        updates["name"] = new_name

    # Категория
    console.print("\n  Текущая категория: [cyan]{m.category}[/]")
    if Confirm.ask("  Изменить категорию?", default=False):
        console.print()
        for k, (val, label) in CATEGORIES.items():
            console.print(f"  [yellow]{k}[/]  {label}")
        key = Prompt.ask("  Выбери", choices=list(CATEGORIES.keys()))
        updates["category"] = CATEGORIES[key][0]

        sub_opts = SUBCATEGORIES.get(updates["category"], {})
        if sub_opts:
            console.print()
            for k, (val, label) in sub_opts.items():
                console.print(f"  [yellow]{k}[/]  {label}")
            sub_key = Prompt.ask("  Подкатегория", choices=list(sub_opts.keys()))
            updates["subcategory"] = sub_opts[sub_key][0]

    # Назначение
    if Confirm.ask("  Изменить назначение?", default=False):
        console.print()
        for k, (val, label) in PURPOSES.items():
            console.print(f"  [yellow]{k}[/]  {label}")
        key = Prompt.ask("  Выбери", choices=list(PURPOSES.keys()))
        updates["purpose"] = PURPOSES[key][0]

    # Заметки
    new_notes = Prompt.ask("Заметки", default=m.notes or "")
    if new_notes != (m.notes or ""):
        updates["notes"] = new_notes or None

    # Перемаппинг полей
    if Confirm.ask("\n  Перенастроить маппинг полей?", default=False):
        new_fields = _edit_fields(m.fields)
        updates["fields"] = new_fields

    if not updates:
        console.print("[dim]Изменений нет.[/]")
        return

    result = storage.update(mapping_id, **updates)
    if result:
        console.print(f"\n[bold green]✅ Маппинг #{mapping_id} обновлён.[/]")
    else:
        console.print(f"[red]Ошибка обновления.[/]")


def _edit_fields(existing_fields) -> list[FieldMapping]:
    """Позволяет пересмотреть маппинг каждого поля."""
    new_fields = []
    console.print()
    for f in existing_fields:
        console.print(
            f"\n  [white]{f.source_column}[/] → "
            f"[green]{f.target_field}[/] "
            f"[yellow]({f.data_type})[/]"
        )
        if not Confirm.ask("  Изменить?", default=False):
            new_fields.append(FieldMapping(
                source_column=f.source_column,
                target_field=f.target_field,
                data_type=f.data_type,
                date_format=f.date_format,
                is_required=f.is_required,
            ))
            continue

        # Выбор нового поля
        console.print()
        items = list(TARGET_FIELDS.items())
        for i, (key, label) in enumerate(items[:20], 1):
            console.print(f"  [yellow]{i:>2}[/]  [cyan]{key:<15}[/] {label}")

        raw = Prompt.ask("  Введи номер или имя поля")
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            target = items[int(raw)-1][0]
        elif raw in TARGET_FIELDS:
            target = raw
        else:
            target = raw

        # Тип
        console.print()
        for k, (val, label) in DATA_TYPES.items():
            console.print(f"  [yellow]{k}[/]  {label}")
        type_key = Prompt.ask("  Тип данных", choices=list(DATA_TYPES.keys()), default="1")
        data_type = DATA_TYPES[type_key][0]

        date_format = None
        if data_type == "date":
            console.print()
            for k, (val, label) in DATE_FORMATS.items():
                console.print(f"  [yellow]{k}[/]  {label}")
            fmt_key = Prompt.ask("  Формат даты", choices=list(DATE_FORMATS.keys()), default="6")
            date_format = DATE_FORMATS[fmt_key][0]

        is_required = Confirm.ask("  Обязательная?", default=False)

        new_fields.append(FieldMapping(
            source_column=f.source_column,
            target_field=target,
            data_type=data_type,
            date_format=date_format,
            is_required=is_required,
        ))

    return new_fields


# ── delete ───────────────────────────────────────────────
@mappings.command("delete")
@click.argument("mapping_id", type=int)
@click.option("--hard", is_flag=True, default=False, help="Удалить насовсем (не деактивировать)")
@click.option("--db", is_flag=True, default=False)
@click.option("--yes", "-y", is_flag=True, default=False, help="Не спрашивать подтверждения")
def mappings_delete(mapping_id: int, hard: bool, db: bool, yes: bool):
    """Удалить маппинг (мягко или насовсем)."""
    storage = _get_storage(db)
    m = storage.get_by_id(mapping_id)

    if not m:
        console.print(f"[red]Маппинг id={mapping_id} не найден.[/]")
        raise SystemExit(1)

    action = "УДАЛИТЬ НАСОВСЕМ" if hard else "деактивировать"
    console.print(f"\n  Маппинг: [bold]{m.name}[/] (id={mapping_id})")
    console.print(f"  Действие: [red]{action}[/]\n")

    if not yes and not Confirm.ask(f"  Подтвердить {action}?", default=False):
        console.print("[dim]Отменено.[/]")
        return

    ok = storage.delete(mapping_id, hard=hard)
    if ok:
        word = "Удалён" if hard else "Деактивирован"
        console.print(f"[bold green]✅ {word}: маппинг #{mapping_id} '{m.name}'[/]")
    else:
        console.print(f"[red]Ошибка удаления.[/]")


# ── export ───────────────────────────────────────────────
@mappings.command("export")
@click.argument("path", default="", required=False)
@click.option("--db", is_flag=True, default=False)
def mappings_export(path: str, db: bool):
    """Экспортировать маппинги в JSON."""
    storage = _get_storage(db)
    out = Path(path) if path else None
    result = storage.export_json(out)
    all_m = storage.get_all(active_only=False)
    console.print(f"[bold green]✅ Экспортировано {len(all_m)} маппингов → {result}[/]")


# ── import ───────────────────────────────────────────────
@mappings.command("import")
@click.argument("path")
@click.option("--db", is_flag=True, default=False)
def mappings_import(path: str, db: bool):
    """Импортировать маппинги из JSON."""
    p = Path(path)
    if not p.exists():
        console.print(f"[red]Файл не найден: {p}[/]")
        raise SystemExit(1)
    storage = _get_storage(db)
    count = storage.import_json(p)
    console.print(f"[bold green]✅ Импортировано {count} новых маппингов из {p.name}[/]")


# ─────────────────────────────────────────────────────────
# Команды системы (локальный режим по умолчанию)
# ─────────────────────────────────────────────────────────
def _make_pipeline(db: bool, interactive: bool):
    """SmartPipeline (по умолчанию) или интерактивный Pipeline."""
    if interactive:
        from pipeline import Pipeline
        return Pipeline(use_db=db), "interactive"
    from smart_pipeline import SmartPipeline
    return SmartPipeline(use_db=db), "smart"


@cli.command("run")
@click.option("--db", is_flag=True, default=False, help="PostgreSQL (иначе JSON в data/)")
@click.option("--scan/--no-scan", default=True, help="Обработать файлы в incoming/ при старте")
@click.option(
    "--interactive", is_flag=True, default=False,
    help="Ручной маппинг в терминале (старый режим)",
)
def run_watcher(db: bool, scan: bool, interactive: bool):
    """Следить за incoming/ и обрабатывать новые отчёты WB."""
    p, mode = _make_pipeline(db, interactive)

    console.print(Panel(
        "[bold green]▶  WB Processor — локальный режим[/]\n"
        f"Режим:     [cyan]{mode}[/]\n"
        f"Хранилище: [{'PostgreSQL' if db else 'JSON → data/'}]\n"
        f"Папка:     [cyan]{p.incoming_dir}[/]\n"
        "Кладите .xlsx / .csv в incoming/  |  Остановка: [bold]Ctrl+C[/]",
        box=box.ROUNDED,
    ))

    if scan:
        p.scan_existing()

    p.run_forever()


@cli.command("scan")
@click.option("--db", is_flag=True, default=False)
@click.option("--interactive", is_flag=True, default=False, help="Ручной маппинг")
def scan_cmd(db: bool, interactive: bool):
    """Один проход: все файлы из incoming/."""
    p, mode = _make_pipeline(db, interactive)
    console.print(f"[cyan]Сканирование incoming/ (режим: {mode})...[/]")
    p.scan_existing()
    if mode == "smart" and hasattr(p, "queue_stats"):
        qs = p.queue_stats()
        pending = qs.get("review_queue", {}).get("pending", 0)
        if pending:
            console.print(
                f"[yellow]⚠  {pending} колонок ждут проверки — "
                f"команда: [bold]python main.py review list[/][/]"
            )
    console.print("[bold green]✅ Готово.[/]")


@cli.group()
def review():
    """Колонки с низкой уверенностью маппинга (без API)."""
    pass


@review.command("list")
@click.option("--db", is_flag=True, default=False)
def review_list(db: bool):
    """Показать очередь проверки маппинга."""
    from review_queue.queue_store import ReviewQueue

    queue = ReviewQueue(use_db=db)
    items = queue.get_pending()
    if not items:
        console.print("[green]Очередь пуста — все колонки с достаточной уверенностью.[/]")
        return

    table = Table(title=f"Review queue ({len(items)})", box=box.ROUNDED)
    table.add_column("ID", style="dim", max_width=36)
    table.add_column("Файл", style="white")
    table.add_column("Колонка", style="cyan")
    table.add_column("→ Поле", style="green")
    table.add_column("Conf", justify="right")
    for it in items[:30]:
        table.add_row(
            it.id[:34],
            it.filename,
            it.source_column,
            it.suggested_field or "—",
            f"{it.confidence_score:.0%}",
        )
    console.print(table)
    if len(items) > 30:
        console.print(f"[dim]… и ещё {len(items) - 30}[/]")


@review.command("approve")
@click.argument("item_id")
@click.option("--field", "-f", default=None, help="Целевое поле (если не suggested)")
@click.option("--db", is_flag=True, default=False)
def review_approve(item_id: str, field: str, db: bool):
    """Подтвердить маппинг колонки."""
    from review_queue.queue_store import ReviewQueue
    from smart_pipeline import SmartPipeline

    queue = ReviewQueue(use_db=db)
    item = queue.approve(item_id, field=field)
    if not item:
        console.print(f"[red]Item не найден: {item_id}[/]")
        raise SystemExit(1)
    p = SmartPipeline(use_db=db)
    applied = p.apply_pending_reviews(item.struct_hash)
    console.print(f"[green]✅ {item.source_column} → {item.correct_field}[/] (learning: {applied})")


@cli.command("status")
@click.option("--db", is_flag=True, default=False)
def status_cmd(db: bool):
    """Статус: папки, маппинги, данные, реестр."""
    from config.settings import INCOMING_DIR, PROCESSED_DIR, FAILED_DIR, DATA_DIR
    from core.processed_registry import ProcessedFileRegistry
    from review_queue.queue_store import ReviewQueue

    storage = _get_storage(db)
    repo = MappingRepository(storage)
    stats = repo.stats()
    reg = ProcessedFileRegistry().stats()
    rq = ReviewQueue(use_db=db).stats()

    def _count_files(d: Path) -> int:
        if not d.exists():
            return 0
        return sum(1 for f in d.iterdir() if f.is_file() and not f.name.startswith("."))

    data_files = {
        "mappings.json": DATA_DIR / "mappings.json",
        "transactions.json": DATA_DIR / "loaded" / "transactions.json",
        "products.json": DATA_DIR / "loaded" / "products.json",
        "stocks.json": DATA_DIR / "loaded" / "stocks.json",
    }
    data_lines = []
    for name, path in data_files.items():
        if path.exists():
            try:
                import json
                n = len(json.loads(path.read_text(encoding="utf-8")))
                data_lines.append(f"  {name}: [yellow]{n}[/] записей")
            except Exception:
                data_lines.append(f"  {name}: [dim]есть[/]")
        else:
            data_lines.append(f"  {name}: [dim]—[/]")

    try:
        from smart_mapping.kb_integration import get_knowledge_engine
        kb = get_knowledge_engine().stats()
        kb_line = (
            f"\n[bold]Knowledge Base[/]\n"
            f"  Полей реестра: [yellow]{kb.get('total_fields', 0)}[/]\n"
            f"  Аналитика / служебные: [green]{kb.get('analytics_fields', 0)}[/] / "
            f"[dim]{kb.get('service_fields', 0)}[/]\n"
            f"  Терминов оферты (PDF): [cyan]{kb.get('pdf_terms', 0)}[/]"
        )
    except Exception:
        kb_line = ""

    console.print(Panel(
        f"[bold]Маппинги[/]\n"
        f"  Всего: [yellow]{stats['total']}[/]  Активных: [green]{stats['active']}[/]\n"
        f"  Категории: {stats['by_category']}\n\n"
        f"[bold]Папки[/]\n"
        f"  incoming/:  [cyan]{_count_files(INCOMING_DIR)}[/]\n"
        f"  processed/: [green]{_count_files(PROCESSED_DIR)}[/]\n"
        f"  failed/:    [red]{_count_files(FAILED_DIR)}[/]\n\n"
        f"[bold]Реестр файлов[/] (без повторной загрузки)\n"
        f"  Обработано: [green]{reg.get('total', 0)}[/]  {reg.get('by_status', {})}\n\n"
        f"[bold]Review[/]  pending: [yellow]{rq.get('pending', 0)}[/]\n\n"
        f"[bold]Данные[/] (data/)\n" + "\n".join(data_lines)
        + kb_line,
        title="[bold]WB Processor — локальный статус[/]",
        box=box.ROUNDED,
    ))

    # Ошибки из лога
    error_log = Path(__file__).resolve().parent.parent / "data" / "errors.json"
    if error_log.exists():
        import json
        try:
            errors = json.loads(error_log.read_text())
            recent = [e for e in errors if not e.get("resolved")][-5:]
            if recent:
                console.print(f"\n[bold red]Последние {len(recent)} ошибок:[/]")
                for e in recent:
                    console.print(f"  [{e['severity'].upper()}] {e['stage']}: {e['message'][:80]}")
        except Exception:
            pass
