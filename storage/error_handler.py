"""
ErrorHandler — централизованная обработка ошибок всего pipeline.

Реагирует на:
  - пропавшие обязательные колонки → уведомление + пауза pipeline
  - изменение типа данных → предложение переконфигурировать маппинг
  - ошибки чтения файла → перемещение в failed/
  - ошибки загрузки в БД → retry или skip
  - неизвестный формат файла → запуск InteractiveMapper

Уведомления:
  - лог (всегда)
  - rich console print (если интерактивный режим)
  - опционально: файл-очередь ошибок для мониторинга
"""
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich import box

from config.settings import FAILED_DIR, PROCESSED_DIR
from parsers.parser_engine import ParseResult
from normalizers.normalizer import NormalizeResult
from storage.data_loader import LoadResult

logger = logging.getLogger(__name__)
console = Console()

_ERROR_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "errors.json"


class ErrorSeverity(Enum):
    INFO    = "info"
    WARNING = "warning"
    ERROR   = "error"
    FATAL   = "fatal"


@dataclass
class PipelineError:
    severity: ErrorSeverity
    stage: str                    # parse / normalize / load / classify / watch
    filepath: Path
    message: str
    details: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    resolved: bool = False


# ─────────────────────────────────────────────────────────
# ErrorHandler
# ─────────────────────────────────────────────────────────
class ErrorHandler:
    """
    Использование:
        eh = ErrorHandler()
        eh.handle_parse_result(parse_result)
        eh.handle_normalize_result(norm_result)
        eh.handle_load_result(load_result)
    """

    def __init__(self, interactive: bool = True):
        self._interactive = interactive
        self._errors: list[PipelineError] = []
        _ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ── Parse ─────────────────────────────────────────────

    def handle_parse_result(self, result: ParseResult) -> bool:
        """
        Проверяет ParseResult.
        Возвращает True если можно продолжать pipeline, False — стоп.
        """
        ok = True

        # Обязательные колонки пропали — стоп
        if result.missing_required:
            for col in result.missing_required:
                err = PipelineError(
                    severity=ErrorSeverity.ERROR,
                    stage="parse",
                    filepath=result.filepath,
                    message=f"Обязательная колонка пропала: '{col}'",
                    details=(
                        f"Файл: {result.filepath.name}\n"
                        f"Колонка в маппинге: '{col}'\n"
                        f"Доступные колонки: {result.extra_columns[:10]}"
                    ),
                )
                self._record(err)
                if self._interactive:
                    self._print_error(err)
            ok = False

        # Опциональные пропали — предупреждение
        if result.missing_optional:
            err = PipelineError(
                severity=ErrorSeverity.WARNING,
                stage="parse",
                filepath=result.filepath,
                message=f"Опциональные колонки отсутствуют: {result.missing_optional}",
            )
            self._record(err)
            logger.warning(f"[error_handler] {err.message}")

        # Файл полностью нечитаем
        if not result.ok and not result.missing_required:
            err = PipelineError(
                severity=ErrorSeverity.FATAL,
                stage="parse",
                filepath=result.filepath,
                message="Файл не распознан — нет ни одной маппированной колонки",
                details="\n".join(result.warnings),
            )
            self._record(err)
            if self._interactive:
                self._print_error(err)
            self._move_to_failed(result.filepath, "unrecognized")
            ok = False

        return ok

    # ── Normalize ─────────────────────────────────────────

    def handle_normalize_result(self, result: NormalizeResult) -> bool:
        """Проверяет NormalizeResult. True — продолжать."""
        if not result.ok:
            err = PipelineError(
                severity=ErrorSeverity.ERROR,
                stage="normalize",
                filepath=result.filepath,
                message="Нормализация провалилась",
                details="\n".join(result.warnings),
            )
            self._record(err)
            if self._interactive:
                self._print_error(err)
            return False

        # Сообщаем о колонках с ошибками типов
        if result.type_errors:
            for col, count in result.type_errors.items():
                err = PipelineError(
                    severity=ErrorSeverity.WARNING,
                    stage="normalize",
                    filepath=result.filepath,
                    message=f"Колонка '{col}': {count} значений не приведены к типу",
                )
                self._record(err)
                if self._interactive:
                    console.print(
                        f"  [yellow]⚠[/] {err.message} "
                        f"[dim]({result.filepath.name})[/]"
                    )

        return True

    # ── Load ──────────────────────────────────────────────

    def handle_load_result(self, result: LoadResult) -> bool:
        """Проверяет LoadResult. True — успех."""
        if not result.ok:
            err = PipelineError(
                severity=ErrorSeverity.ERROR,
                stage="load",
                filepath=result.filepath,
                message=f"Ошибка загрузки в БД: {'; '.join(result.errors)}",
            )
            self._record(err)
            if self._interactive:
                self._print_error(err)
            return False

        if result.rows_skipped > 0:
            logger.warning(
                f"[error_handler] {result.filepath.name}: "
                f"{result.rows_skipped} строк пропущено при загрузке"
            )

        return True

    # ── Type change detection ─────────────────────────────

    def check_type_change(
        self,
        col: str,
        expected_type: str,
        sample_values: list,
        filepath: Path,
    ) -> bool:
        """
        Определяет изменился ли тип данных в колонке.
        Возвращает True если всё ок, False если тип изменился.
        """
        actual = self._infer_type(sample_values)
        if actual and actual != expected_type:
            err = PipelineError(
                severity=ErrorSeverity.WARNING,
                stage="normalize",
                filepath=filepath,
                message=(
                    f"Колонка '{col}': ожидался тип '{expected_type}', "
                    f"но данные выглядят как '{actual}'"
                ),
                details=f"Примеры значений: {sample_values[:5]}",
            )
            self._record(err)
            if self._interactive:
                console.print(f"\n  [yellow]⚠  Изменился тип данных[/]")
                console.print(f"  Колонка:   [cyan]{col}[/]")
                console.print(f"  Маппинг:   {expected_type}")
                console.print(f"  Данные:    {actual}")
                console.print(f"  Файл:      {filepath.name}\n")
                from rich.prompt import Confirm
                return not Confirm.ask(
                    "  Переконфигурировать маппинг для этой колонки?",
                    default=False,
                )
            return False
        return True

    # ── File management ───────────────────────────────────

    def move_to_processed(self, filepath: Path) -> Optional[Path]:
        """Перемещает успешно обработанный файл в processed/."""
        try:
            PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
            dest = PROCESSED_DIR / f"{datetime.utcnow():%Y%m%d_%H%M%S}_{filepath.name}"
            shutil.move(str(filepath), str(dest))
            logger.info(f"[error_handler] Moved to processed: {dest.name}")
            return dest
        except Exception as e:
            logger.error(f"[error_handler] Cannot move to processed: {e}")
            return None

    def _move_to_failed(self, filepath: Path, reason: str = "") -> Optional[Path]:
        """Перемещает проблемный файл в failed/."""
        try:
            FAILED_DIR.mkdir(parents=True, exist_ok=True)
            suffix = f"_{reason}" if reason else ""
            dest = FAILED_DIR / f"{datetime.utcnow():%Y%m%d_%H%M%S}{suffix}_{filepath.name}"
            if filepath.exists():
                shutil.move(str(filepath), str(dest))
                logger.warning(f"[error_handler] Moved to failed: {dest.name}")
            return dest
        except Exception as e:
            logger.error(f"[error_handler] Cannot move to failed: {e}")
            return None

    # ── Stats & reporting ─────────────────────────────────

    def get_errors(
        self,
        severity: Optional[ErrorSeverity] = None,
        stage: Optional[str] = None,
    ) -> list[PipelineError]:
        result = self._errors
        if severity:
            result = [e for e in result if e.severity == severity]
        if stage:
            result = [e for e in result if e.stage == stage]
        return result

    def has_fatal(self) -> bool:
        return any(e.severity == ErrorSeverity.FATAL for e in self._errors)

    def summary(self) -> dict:
        by_sev = {}
        for e in self._errors:
            k = e.severity.value
            by_sev[k] = by_sev.get(k, 0) + 1
        return {
            "total": len(self._errors),
            "by_severity": by_sev,
            "has_fatal": self.has_fatal(),
        }

    def clear(self):
        self._errors.clear()

    def persist_errors(self):
        """Дозаписывает ошибки в errors.json для мониторинга."""
        existing = []
        if _ERROR_LOG_PATH.exists():
            try:
                with open(_ERROR_LOG_PATH, encoding="utf-8") as f:
                    content = f.read().strip()
                    existing = json.loads(content) if content else []
            except (json.JSONDecodeError, ValueError):
                existing = []

        new_entries = [
            {
                "severity": e.severity.value,
                "stage": e.stage,
                "filepath": str(e.filepath),
                "message": e.message,
                "details": e.details,
                "timestamp": e.timestamp,
                "resolved": e.resolved,
            }
            for e in self._errors
        ]
        existing.extend(new_entries)

        # Храним последние 1000 ошибок
        if len(existing) > 1000:
            existing = existing[-1000:]

        with open(_ERROR_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    # ── Internal ──────────────────────────────────────────

    def _record(self, err: PipelineError):
        self._errors.append(err)
        if err.severity == ErrorSeverity.FATAL:
            logger.critical(f"[FATAL][{err.stage}] {err.message}")
        elif err.severity == ErrorSeverity.ERROR:
            logger.error(f"[ERROR][{err.stage}] {err.message}")
        elif err.severity == ErrorSeverity.WARNING:
            logger.warning(f"[WARN][{err.stage}] {err.message}")
        else:
            logger.info(f"[INFO][{err.stage}] {err.message}")

    def _print_error(self, err: PipelineError):
        color = {"fatal": "red", "error": "red", "warning": "yellow", "info": "cyan"}
        c = color.get(err.severity.value, "white")
        icon = {"fatal": "💀", "error": "⛔", "warning": "⚠️", "info": "ℹ️"}
        i = icon.get(err.severity.value, "•")
        title = f"{i}  [{err.severity.value.upper()}] {err.stage.upper()}"
        body = err.message
        if err.details:
            body += f"\n\n[dim]{err.details}[/]"
        console.print(Panel(body, title=title, border_style=c, box=box.ROUNDED))

    @staticmethod
    def _infer_type(values: list) -> Optional[str]:
        """Быстрый вывод типа из списка значений."""
        non_null = [v for v in values if v is not None and str(v).strip()]
        if not non_null:
            return None

        # Дата?
        date_patterns = [r"\d{2}\.\d{2}\.\d{4}", r"\d{4}-\d{2}-\d{2}"]
        import re
        date_hits = sum(
            1 for v in non_null
            if any(re.match(p, str(v).strip()) for p in date_patterns)
        )
        if date_hits / len(non_null) > 0.8:
            return "date"

        # Float?
        float_hits = 0
        for v in non_null:
            try:
                s = str(v).replace(",", ".").replace(" ", "")
                float(s)
                float_hits += 1
            except (ValueError, TypeError):
                pass
        if float_hits / len(non_null) > 0.8:
            # Int или float?
            int_hits = sum(1 for v in non_null if str(v).strip().lstrip("-").isdigit())
            return "int" if int_hits / len(non_null) > 0.8 else "float"

        return "str"
