"""
InteractiveMapper — задаёт пользователю вопросы о новом файле.
Результат: заполненный MappingConfig готовый к сохранению.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from classification.file_classifier import ClassificationResult
from mapping.constants import (
    CATEGORIES, SUBCATEGORIES, TARGET_FIELDS,
    DATA_TYPES, PURPOSES, DATE_FORMATS,
)

logger = logging.getLogger(__name__)
console = Console()


# ─────────────────────────────────────────────────────────
# Результат маппинга — передаётся в MappingStorage
# ─────────────────────────────────────────────────────────
@dataclass
class FieldMapping:
    source_column: str
    target_field: str
    data_type: str
    date_format: Optional[str] = None
    is_required: bool = False
    description: Optional[str] = None


@dataclass
class MappingConfig:
    name: str
    struct_hash: str
    category: str
    subcategory: str
    purpose: str
    raw_columns: list[str]
    column_count: int
    fields: list[FieldMapping] = field(default_factory=list)
    notes: Optional[str] = None


# ─────────────────────────────────────────────────────────
# Helpers UI
# ─────────────────────────────────────────────────────────
def _header(text: str):
    console.print(Panel(Text(text, style="bold cyan"), box=box.ROUNDED, expand=False))


def _ask(prompt: str, options: dict, allow_skip: bool = False) -> str:
    """
    Выводит меню и возвращает код выбора.
    options = {"1": (value, label), ...}
    """
    console.print()
    for key, (_, label) in options.items():
        console.print(f"  [bold yellow]{key}[/]  {label}")
    if allow_skip:
        console.print("  [dim]s  → пропустить[/]")
    console.print()

    valid = set(options.keys())
    if allow_skip:
        valid.add("s")

    while True:
        raw = console.input(f"[bold green]{prompt}[/] ").strip()
        if raw in valid:
            return raw
        console.print(f"  [red]Введи одно из: {', '.join(sorted(valid))}[/]")


def _ask_free(prompt: str, default: str = "") -> str:
    """Свободный ввод строки."""
    console.print()
    hint = f" [dim](Enter = '{default}')[/]" if default else ""
    val = console.input(f"[bold green]{prompt}{hint}[/] ").strip()
    return val if val else default


def _ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "[bold]Y[/]/n" if default else "y/[bold]N[/]"
    while True:
        raw = console.input(f"[bold green]{prompt} [{hint}][/] ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "д", "yes", "да"):
            return True
        if raw in ("n", "н", "no", "нет"):
            return False


def _show_sample(result: ClassificationResult):
    """Показывает первые строки файла в таблице."""
    df = result.signature.sample
    table = Table(
        title=f"📄 {result.signature.filepath.name}  "
              f"[dim]({result.signature.column_count} колонок, "
              f"~{result.signature.row_count_estimate} строк)[/]",
        box=box.SIMPLE_HEAD,
        show_lines=False,
        style="dim",
        header_style="bold white",
    )
    for col in df.columns:
        table.add_column(str(col), max_width=20, overflow="ellipsis")
    for _, row in df.head(5).iterrows():
        table.add_row(*[str(v) if v is not None else "" for v in row])
    console.print(table)


def _show_columns_summary(columns: list[str], field_mappings: list[FieldMapping]):
    """Показывает итоговую таблицу маппинга."""
    table = Table(title="📋 Итоговый маппинг", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Колонка в файле", style="white")
    table.add_column("→ Целевое поле", style="green")
    table.add_column("Тип", style="yellow")
    table.add_column("Обязательная", style="magenta")

    mapped = {fm.source_column: fm for fm in field_mappings}
    for col in columns:
        fm = mapped.get(col)
        if fm:
            req = "✅" if fm.is_required else ""
            target = fm.target_field
            dtype = fm.data_type
            if fm.target_field == "ignore":
                target = "[dim]— пропустить —[/]"
                dtype = ""
        else:
            target = "[dim]не задано[/]"
            dtype = ""
            req = ""
        table.add_row(col, target, dtype, req)

    console.print(table)


# ─────────────────────────────────────────────────────────
# InteractiveMapper
# ─────────────────────────────────────────────────────────
class InteractiveMapper:
    """
    Диалог с пользователем для настройки нового формата файла.

    Использование:
        mapper = InteractiveMapper()
        config = mapper.run(classification_result)
        # config: MappingConfig — передать в MappingStorage.save()
    """

    def run(self, result: ClassificationResult) -> MappingConfig:
        console.print()
        _header(f"🆕 Новый формат файла: {result.signature.filepath.name}")
        console.print(
            f"  Хэш структуры: [dim]{result.signature.struct_hash}[/]\n"
            f"  Система задаст несколько вопросов и запомнит настройки.\n"
            f"  [bold]Следующий похожий файл обработается автоматически.[/]\n"
        )

        # 1. Показать файл
        _show_sample(result)

        # 2. Имя конфигурации
        suggested_name = result.signature.filepath.stem.replace("_", " ").title()
        name = _ask_free("Дай название этому формату файла:", default=suggested_name)

        # 3. Категория
        _header("📂 Шаг 1 из 4 — Категория файла")
        cat_key = _ask("Выбери категорию:", CATEGORIES)
        category, _ = CATEGORIES[cat_key]

        # 4. Подкатегория
        _header("📂 Шаг 2 из 4 — Подкатегория")
        sub_options = SUBCATEGORIES[category]
        sub_key = _ask("Выбери подкатегорию:", sub_options)
        subcategory, _ = sub_options[sub_key]

        # 5. Назначение
        _header("🎯 Шаг 3 из 4 — Как использовать данные?")
        purpose_key = _ask("Назначение файла:", PURPOSES)
        purpose, _ = PURPOSES[purpose_key]

        # 6. Маппинг колонок
        _header(f"🗂️  Шаг 4 из 4 — Маппинг колонок ({result.signature.column_count} шт.)")
        console.print(
            "  Для каждой колонки укажи что она означает.\n"
            "  Если колонка не нужна — выбери [bold yellow]ignore[/].\n"
        )

        field_mappings = self._map_columns(result.signature.columns)

        # 7. Итог
        _show_columns_summary(result.signature.columns, field_mappings)

        # 8. Заметки
        notes = _ask_free("Заметки (необязательно, Enter чтобы пропустить):", default="")

        # 9. Подтверждение
        console.print()
        if not _ask_yes_no("Сохранить этот маппинг?", default=True):
            console.print("[yellow]Отменено. Файл будет пропущен.[/]")
            raise InterruptedError("User cancelled mapping.")

        config = MappingConfig(
            name=name,
            struct_hash=result.signature.struct_hash,
            category=category,
            subcategory=subcategory,
            purpose=purpose,
            raw_columns=result.signature.columns,
            column_count=result.signature.column_count,
            fields=field_mappings,
            notes=notes or None,
        )

        console.print(f"\n[bold green]✅ Маппинг '[cyan]{name}[/]' сохранён![/]\n")
        return config

    # ─────────────────────────────────────────────────────
    def _map_columns(self, columns: list[str]) -> list[FieldMapping]:
        """Итерирует по колонкам, спрашивает маппинг для каждой."""
        field_mappings: list[FieldMapping] = []
        total = len(columns)

        for idx, col in enumerate(columns, 1):
            console.print(f"\n[bold white]── Колонка {idx}/{total}: [cyan]{col}[/] ──[/]")

            # Авто-предложение по имени колонки
            suggestion = self._suggest_target(col)
            if suggestion:
                console.print(f"  💡 Похоже на: [yellow]{TARGET_FIELDS.get(suggestion, suggestion)}[/]")
                if _ask_yes_no(f"  Использовать '{suggestion}'?", default=True):
                    target_field = suggestion
                    data_type = self._default_type_for(target_field)
                    date_format = self._ask_date_format() if data_type == "date" else None
                    is_required = _ask_yes_no("  Обязательная колонка?", default=False)
                    field_mappings.append(FieldMapping(
                        source_column=col,
                        target_field=target_field,
                        data_type=data_type,
                        date_format=date_format,
                        is_required=is_required,
                    ))
                    continue

            # Ручной выбор
            target_field = self._ask_target_field(col)

            if target_field == "ignore":
                field_mappings.append(FieldMapping(
                    source_column=col,
                    target_field="ignore",
                    data_type="str",
                ))
                continue

            # Тип данных
            console.print()
            type_key = _ask("  Тип данных:", DATA_TYPES)
            data_type, _ = DATA_TYPES[type_key]

            date_format = None
            if data_type == "date":
                date_format = self._ask_date_format()

            is_required = _ask_yes_no("  Обязательная колонка?", default=False)

            field_mappings.append(FieldMapping(
                source_column=col,
                target_field=target_field,
                data_type=data_type,
                date_format=date_format,
                is_required=is_required,
            ))

        return field_mappings

    def _ask_target_field(self, col: str) -> str:
        """Показывает список полей и позволяет выбрать или ввести своё."""
        # Разбиваем на страницы по 10
        items = list(TARGET_FIELDS.items())
        per_page = 12
        page = 0
        pages = (len(items) + per_page - 1) // per_page

        while True:
            console.print(f"\n  [dim]Страница {page + 1}/{pages}[/]")
            chunk = items[page * per_page:(page + 1) * per_page]
            for i, (key, label) in enumerate(chunk, 1):
                console.print(f"  [bold yellow]{i:>2}[/]  [cyan]{key:<15}[/] {label}")
            console.print()
            if pages > 1:
                console.print("  [dim]n → следующая страница   p → предыдущая[/]")
            console.print("  [dim]Введи номер или само имя поля:[/]")

            raw = console.input("  [bold green]→[/] ").strip()

            if raw.lower() == "n" and page < pages - 1:
                page += 1
                continue
            if raw.lower() == "p" and page > 0:
                page -= 1
                continue

            # По номеру
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(chunk):
                    return chunk[idx][0]

            # По имени
            if raw in TARGET_FIELDS:
                return raw

            # Своё имя
            if raw:
                confirm = _ask_yes_no(f"  Использовать своё поле '[cyan]{raw}[/]'?", default=True)
                if confirm:
                    return raw

            console.print("  [red]Не понял. Введи номер или имя поля.[/]")

    def _ask_date_format(self) -> str:
        console.print()
        fmt_key = _ask("  Формат даты:", DATE_FORMATS)
        fmt, _ = DATE_FORMATS[fmt_key]
        if fmt == "auto":
            return "auto"
        return fmt

    @staticmethod
    def _suggest_target(col: str) -> Optional[str]:
        """
        Эвристика: предлагает target_field по имени колонки.
        Ключи — подстроки (нижний регистр).
        """
        col_lower = col.lower().strip()

        rules = [
            (["артикул wb", "nmid", "nm_id", "nmid", "sku wb"],               "sku"),
            (["артикул", "sku", "арт "],                                        "sku"),
            (["баркод", "barcode", "штрих"],                                    "barcode"),
            (["наименование", "название", "предмет", "name", "товар"],          "name"),
            (["бренд", "brand"],                                                 "brand"),
            (["категория", "category", "подкатегория"],                         "category"),
            (["дата", "date", "период", "месяц"],                               "date"),
            (["количество", "кол-во", "qty", "quantity", "шт"],                 "quantity"),
            (["цена розн", "цена продажи", "розничная цена", "price"],          "price"),
            (["себестоим", "cost"],                                              "cost_price"),
            (["выручка", "revenue", "оборот"],                                   "revenue"),
            (["комиссия", "commission", "вознаграждение"],                       "commission"),
            (["логистика", "logistics", "доставка"],                             "logistics"),
            (["прибыль", "profit"],                                               "net_profit"),
            (["склад", "warehouse", "офис"],                                     "warehouse"),
            (["регион", "region", "область"],                                    "region"),
            (["расход", "затрат", "spend", "бюджет"],                            "ad_spend"),
            (["показ", "impression"],                                             "impressions"),
            (["клик", "click"],                                                   "clicks"),
            (["остаток", "stock", "запас"],                                      "quantity"),
            (["резерв", "reserved"],                                              "reserved"),
            (["в пути", "transit"],                                               "in_transit"),
        ]

        for keywords, target in rules:
            if any(kw in col_lower for kw in keywords):
                return target
        return None

    @staticmethod
    def _default_type_for(target_field: str) -> str:
        type_map = {
            "sku": "str", "barcode": "str", "name": "str",
            "brand": "str", "category": "str", "warehouse": "str",
            "region": "str", "campaign_id": "str",
            "date": "date",
            "quantity": "int", "reserved": "int",
            "in_transit": "int", "impressions": "int", "clicks": "int",
            "price": "float", "cost_price": "float", "revenue": "float",
            "commission": "float", "logistics": "float", "net_profit": "float",
            "ad_spend": "float", "ctr": "float", "cpc": "float",
        }
        return type_map.get(target_field, "str")
