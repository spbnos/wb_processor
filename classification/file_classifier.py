"""
FileClassifier — определяет формат файла.
Вычисляет struct_hash по именам колонок → ищет в MappingStorage.
Результат: known mapping или None (неизвестный формат).
"""
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import SAMPLE_ROWS, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# Результат классификации
# ─────────────────────────────────────────────────────────
@dataclass
class FileSignature:
    """Сигнатура файла — всё что нужно для классификации."""
    filepath: Path
    extension: str
    columns: list[str]
    column_count: int
    struct_hash: str
    file_hash: str
    sample: pd.DataFrame       # первые N строк для показа пользователю
    row_count_estimate: int
    sheet_name: Optional[str] = None    # для xlsx
    encoding: Optional[str] = None      # для csv
    extra: dict = field(default_factory=dict)


@dataclass
class ClassificationResult:
    signature: FileSignature
    mapping_id: Optional[int]          # None = формат неизвестен
    mapping_name: Optional[str]
    is_known: bool


# ─────────────────────────────────────────────────────────
# Вычисление хэшей
# ─────────────────────────────────────────────────────────
def compute_file_hash(filepath: Path) -> str:
    """SHA256 файла целиком."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def compute_struct_hash(columns: list[str]) -> str:
    """
    SHA256 от нормализованных имён колонок.
    Нормализация: strip + lower + sort → стабильный хэш.
    """
    normalized = sorted(c.strip().lower() for c in columns if c)
    key = "|".join(normalized)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


# ─────────────────────────────────────────────────────────
# Чтение файла
# ─────────────────────────────────────────────────────────
def _detect_encoding(filepath: Path) -> str:
    """Определяет кодировку CSV через chardet."""
    try:
        import chardet
        with open(filepath, "rb") as f:
            raw = f.read(32768)
        result = chardet.detect(raw)
        return result.get("encoding") or "utf-8"
    except Exception:
        return "utf-8"


def _read_file(filepath: Path, nrows: int = SAMPLE_ROWS) -> tuple[pd.DataFrame, dict]:
    """
    Читает файл и возвращает (sample_df, meta).
    meta содержит sheet_name, encoding и т.д.
    """
    ext = filepath.suffix.lower()
    meta: dict = {}

    if ext in {".xlsx", ".xls"}:
        xl = pd.ExcelFile(filepath, engine="openpyxl" if ext == ".xlsx" else None)
        sheet = xl.sheet_names[0]
        meta["sheet_name"] = sheet
        meta["all_sheets"] = xl.sheet_names
        df_full = xl.parse(sheet, header=None, nrows=50)
        header_row = _find_header_row(df_full)
        meta["header_row"] = header_row
        df = xl.parse(sheet, header=header_row, nrows=nrows)

    elif ext == ".csv":
        encoding = _detect_encoding(filepath)
        meta["encoding"] = encoding
        # Пробуем разные разделители
        for sep in [",", ";", "\t", "|"]:
            try:
                df = pd.read_csv(filepath, sep=sep, encoding=encoding, nrows=nrows)
                if len(df.columns) > 1:
                    meta["sep"] = sep
                    break
            except Exception:
                continue
        else:
            df = pd.read_csv(filepath, encoding=encoding, nrows=nrows)
            meta["sep"] = ","

    else:
        raise ValueError(f"Unsupported extension: {ext}")

    # Очистка имён колонок
    df.columns = [str(c).strip() for c in df.columns]
    return df, meta


def _find_header_row(df: pd.DataFrame, max_scan: int = 10) -> int:
    """
    Ищет строку-заголовок в грязном Excel.
    Эвристика: строка где больше всего непустых текстовых значений.
    """
    best_row = 0
    best_score = 0
    for i in range(min(max_scan, len(df))):
        row = df.iloc[i]
        score = sum(1 for v in row if isinstance(v, str) and v.strip())
        if score > best_score:
            best_score = score
            best_row = i
    return best_row


def _estimate_row_count(filepath: Path, ext: str, meta: dict) -> int:
    """Быстрая оценка количества строк без полного чтения."""
    try:
        if ext in {".xlsx", ".xls"}:
            xl = pd.ExcelFile(filepath, engine="openpyxl" if ext == ".xlsx" else None)
            df = xl.parse(meta.get("sheet_name", 0), usecols=[0])
            return len(df)
        elif ext == ".csv":
            with open(filepath, "rb") as f:
                return sum(1 for _ in f) - 1  # минус заголовок
    except Exception:
        return -1
    return -1


# ─────────────────────────────────────────────────────────
# Главный класс
# ─────────────────────────────────────────────────────────
class FileClassifier:
    """
    Классифицирует файл:
    1. Вычисляет struct_hash по колонкам
    2. Ищет в mapping storage совпадение
    3. Возвращает ClassificationResult
    """

    def __init__(self, mapping_storage):
        """
        mapping_storage — объект MappingStorage (будет в Шаге 4).
        Пока принимает duck-typed объект с методом find_by_struct_hash(hash) -> Optional[Mapping].
        """
        self._storage = mapping_storage

    def classify(self, filepath: Path) -> ClassificationResult:
        logger.info(f"[classifier] Classifying: {filepath.name}")

        ext = filepath.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        # 1. Читаем файл
        try:
            sample_df, meta = _read_file(filepath)
        except Exception as e:
            raise RuntimeError(f"Cannot read file {filepath.name}: {e}") from e

        columns = list(sample_df.columns)
        logger.debug(f"[classifier] Columns ({len(columns)}): {columns}")

        # 2. Хэши
        struct_hash = compute_struct_hash(columns)
        file_hash = compute_file_hash(filepath)
        row_count = _estimate_row_count(filepath, ext, meta)

        # 3. Сигнатура
        signature = FileSignature(
            filepath=filepath,
            extension=ext,
            columns=columns,
            column_count=len(columns),
            struct_hash=struct_hash,
            file_hash=file_hash,
            sample=sample_df,
            row_count_estimate=row_count,
            sheet_name=meta.get("sheet_name"),
            encoding=meta.get("encoding"),
            extra=meta,
        )

        # 4. Ищем маппинг
        mapping = self._storage.find_by_struct_hash(struct_hash)

        if mapping:
            logger.info(f"[classifier] Known format: '{mapping.name}' (hash={struct_hash})")
            return ClassificationResult(
                signature=signature,
                mapping_id=mapping.id,
                mapping_name=mapping.name,
                is_known=True,
            )

        logger.info(f"[classifier] Unknown format (hash={struct_hash})")
        return ClassificationResult(
            signature=signature,
            mapping_id=None,
            mapping_name=None,
            is_known=False,
        )
