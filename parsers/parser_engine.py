"""
ParserEngine — применяет MappingConfig к файлу.

Поток:
    filepath + MappingObj → raw DataFrame → mapped DataFrame

Гарантии:
  - переименовывает колонки source → target
  - пропускает колонки с target_field == 'ignore'
  - детектирует пропавшие обязательные колонки
  - не падает на грязных Excel (лишние строки сверху, пустые строки)
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from classification.file_classifier import _find_header_row, _detect_encoding
from mapping.mapping_storage import MappingObj, MappingFieldObj

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    df: pd.DataFrame
    mapping_id: int
    filepath: Path
    row_count: int
    missing_required: list = field(default_factory=list)
    missing_optional: list = field(default_factory=list)
    extra_columns: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    ok: bool = True


def _read_raw(filepath: Path) -> pd.DataFrame:
    """Читает файл, находит заголовок, возвращает сырой DataFrame."""
    ext = filepath.suffix.lower()

    if ext in {".xlsx", ".xls"}:
        engine = "openpyxl" if ext == ".xlsx" else None
        xl = pd.ExcelFile(filepath, engine=engine)
        sheet = xl.sheet_names[0]
        probe = xl.parse(sheet, header=None, nrows=30)
        header_row = _find_header_row(probe)
        df = xl.parse(sheet, header=header_row)

    elif ext == ".csv":
        encoding = _detect_encoding(filepath)
        df = None
        for sep in [",", ";", "\t", "|"]:
            try:
                tmp = pd.read_csv(filepath, sep=sep, encoding=encoding)
                if len(tmp.columns) > 1:
                    df = tmp
                    break
            except Exception:
                continue
        if df is None:
            df = pd.read_csv(filepath, encoding=encoding)
    else:
        raise ValueError(f"Unsupported extension: {ext}")

    df.columns = [str(c).strip().replace("\n", " ").replace("\r", "") for c in df.columns]
    df = df.dropna(how="all").reset_index(drop=True)
    logger.debug(f"[parser] Read {len(df)} rows x {len(df.columns)} cols from {filepath.name}")
    return df


class ParserEngine:
    def parse(self, filepath: Path, mapping: MappingObj) -> ParseResult:
        logger.info(f"[parser] Parsing: {filepath.name} with mapping '{mapping.name}'")

        try:
            raw_df = _read_raw(filepath)
        except Exception as e:
            logger.error(f"[parser] Failed to read {filepath.name}: {e}")
            return ParseResult(
                df=pd.DataFrame(), mapping_id=mapping.id, filepath=filepath,
                row_count=0, warnings=[f"Read error: {e}"], ok=False,
            )

        return self._apply_mapping(raw_df, mapping, filepath)

    def _apply_mapping(self, raw_df: pd.DataFrame, mapping: MappingObj, filepath: Path) -> ParseResult:
        fields: list = mapping.fields
        warnings = []
        missing_required = []
        missing_optional = []

        field_map = {
            f.source_column: f for f in fields
            if f.target_field != "ignore"
        }

        file_cols = set(raw_df.columns)
        mapped_cols = set(field_map.keys())
        found = mapped_cols & file_cols
        not_found = mapped_cols - file_cols
        extra = file_cols - mapped_cols

        for src_col in not_found:
            fm = field_map[src_col]
            if fm.is_required:
                missing_required.append(src_col)
                msg = f"Обязательная колонка пропала: '{src_col}' -> '{fm.target_field}'"
                warnings.append(msg)
                logger.warning(f"[parser] {msg}")
            else:
                missing_optional.append(src_col)

        if not found:
            return ParseResult(
                df=pd.DataFrame(), mapping_id=mapping.id, filepath=filepath,
                row_count=0, missing_required=missing_required,
                missing_optional=missing_optional, extra_columns=list(extra),
                warnings=warnings + ["No mapped columns found - wrong file?"],
                ok=False,
            )

        select_cols = list(found)
        rename_map = {src: field_map[src].target_field for src in found}
        mapped_df = raw_df[select_cols].rename(columns=rename_map)

        logger.info(
            f"[parser] Mapped {len(select_cols)} cols, "
            f"{len(missing_optional)} optional missing, "
            f"{len(missing_required)} required missing"
        )

        return ParseResult(
            df=mapped_df, mapping_id=mapping.id, filepath=filepath,
            row_count=len(mapped_df), missing_required=missing_required,
            missing_optional=missing_optional, extra_columns=list(extra),
            warnings=warnings, ok=len(missing_required) == 0,
        )
