"""
rating_parser.py — «Оценка товара» / «Рейтинг карточки» WB.

Особенности файла:
  - Упакован в ZIP (имя ZIP = пользовательское, произвольное)
  - Внутри один xlsx с листами: Общая информация, Метрики, Фильтры, Детализация по артикулам
  - Период хранится в листе "Общая информация" → "Выбранный период"
  - Данные — в листе "Детализация по артикулам", header=1

КРИТИЧНО: данные НЕЛЬЗЯ смешивать из разных периодов!
Каждый файл сохраняется с ключом period_start+period_end в rating_history.json.
При повторной загрузке того же периода — данные перезаписываются (не дублируются).

Загружается в: data/loaded/product_ratings.json
Исторический архив по периодам: data/rating_history.json
"""
from __future__ import annotations
import io, json, zipfile, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import pandas as pd
import logging
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult

logger = logging.getLogger(__name__)

_HISTORY_PATH = Path(__file__).resolve().parents[2] / "data" / "rating_history.json"

_COL_MAP = {
    "Артикул продавца":                                  "seller_article",
    "Артикул WB":                                        "sku_id",
    "Название":                                          "product_name",
    "Предмет":                                           "subject",
    "Бренд":                                             "brand",
    "Рейтинг карточки":                                  "card_rating",
    "Рейтинг по отзывам":                                "review_rating",
    "Рейтинг по отзывам выше среднего по предмету, %":  "review_above_avg_pct",
    "Все отзывы за период":                              "reviews_total",
    "Отзывы за баллы":                                   "reviews_paid",
    "Оценки 5":                                          "ratings_5",
    "Оценки 4":                                          "ratings_4",
    "Оценки 3":                                          "ratings_3",
    "Оценки 2":                                          "ratings_2",
    "Оценки 1":                                          "ratings_1",
    "Отзывы, исключенные из рейтинга":                  "reviews_excluded",
    "Закрепленный отзыв":                                "has_pinned_review",
    "Участие в акции\n«Баллы за отзывы»":               "in_reviews_promo",
    "Скрытый товар":                                     "is_hidden",
    "Заказы, шт":                                        "orders_qty",
    "Выкупы, шт":                                        "buyouts_qty",
    "Процент выкупа":                                    "buyout_pct",
    "Отмена, шт":                                        "cancellations_qty",
    # Previous period columns
    "Рейтинг по отзывам (предыдущий период)":           "prev_review_rating",
    "Все отзывы за период (предыдущий период)":          "prev_reviews_total",
    "Заказы, шт (предыдущий период)":                   "prev_orders_qty",
    "Выкупы, шт (предыдущий период)":                   "prev_buyouts_qty",
    "Процент выкупа (предыдущий период)":               "prev_buyout_pct",
    "Отмена, шт (предыдущий период)":                   "prev_cancellations_qty",
}


def _parse_period(raw_str: str) -> tuple[str, str]:
    """Extract YYYY-MM-DD dates from 'С 2026-02-02 по 2026-04-21'."""
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", str(raw_str))
    if len(dates) >= 2:
        return dates[0], dates[1]
    elif len(dates) == 1:
        return dates[0], dates[0]
    return "", ""


class RatingParser(BaseDomainParser):
    report_id  = "product_ratings"
    domain     = "content_intelligence"
    db_table   = "product_ratings"
    header_row = 1  # Детализация по артикулам: header at row index 1

    def parse(self, filepath: Path, header_row: int = 1) -> DomainParseResult:
        """Parse rating ZIP or XLSX file."""
        raw_bytes = self._load_bytes(filepath)
        if raw_bytes is None:
            return DomainParseResult(
                report_id=self.report_id, filepath=filepath,
                domain=self.domain, db_table=self.db_table,
                df=pd.DataFrame(), rows=0, ok=False,
                errors=[f"Cannot read: {filepath.name}"],
            )

        # Read metadata: period
        period_from = period_to = ""
        try:
            df_info = pd.read_excel(io.BytesIO(raw_bytes), sheet_name="Общая информация", header=None)
            period_row = df_info[df_info.iloc[:, 0] == "Выбранный период"]
            if not period_row.empty:
                period_from, period_to = _parse_period(str(period_row.iloc[0, 1]))
            prev_row = df_info[df_info.iloc[:, 0] == "Предыдущий период"]
            prev_from = prev_to = ""
            if not prev_row.empty:
                prev_from, prev_to = _parse_period(str(prev_row.iloc[0, 1]))
        except Exception as e:
            logger.warning(f"[rating] Cannot read metadata: {e}")
            prev_from = prev_to = ""

        # Read detail sheet
        try:
            df = pd.read_excel(io.BytesIO(raw_bytes), sheet_name="Детализация по артикулам", header=1)
        except Exception as e:
            return DomainParseResult(
                report_id=self.report_id, filepath=filepath,
                domain=self.domain, db_table=self.db_table,
                df=pd.DataFrame(), rows=0, ok=False,
                errors=[f"Cannot read detail sheet: {e}"],
            )

        # Rename columns
        df = df.rename(columns={k: v for k, v in _COL_MAP.items() if k in df.columns})

        # Clean types
        str_cols = ["seller_article", "sku_id", "product_name", "subject", "brand",
                    "has_pinned_review", "in_reviews_promo", "is_hidden"]
        for c in str_cols:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip().replace("nan", "")

        num_cols = ["card_rating","review_rating","review_above_avg_pct",
                    "reviews_total","reviews_paid","ratings_5","ratings_4",
                    "ratings_3","ratings_2","ratings_1","reviews_excluded",
                    "orders_qty","buyouts_qty","buyout_pct","cancellations_qty",
                    "prev_review_rating","prev_reviews_total","prev_orders_qty",
                    "prev_buyouts_qty","prev_buyout_pct","prev_cancellations_qty"]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(",",".").str.replace("-",""), errors="coerce")

        # Ensure sku_id is string integer
        if "sku_id" in df.columns:
            df["sku_id"] = df["sku_id"].apply(
                lambda v: str(int(float(v))) if pd.notna(v) and str(v) not in ("","nan") else ""
            )

        # Add period metadata to each row
        df["period_from"]   = period_from
        df["period_to"]     = period_to
        df["prev_from"]     = prev_from if "prev_from" in dir() else ""
        df["prev_to"]       = prev_to   if "prev_to"   in dir() else ""
        df["report_type"]   = self.report_id
        df["source_file"]   = filepath.name

        # Drop rows with no sku
        df = df[df["sku_id"].str.len() > 0].copy()

        # Save to historical archive (period-keyed, no mixing)
        self._save_to_history(df, period_from, period_to, filepath.name)

        logger.info(
            f"[rating] Parsed {len(df)} SKUs | period {period_from}→{period_to} "
            f"from {filepath.name}"
        )
        return DomainParseResult(
            report_id=self.report_id, filepath=filepath,
            domain=self.domain, db_table=self.db_table,
            df=df, rows=len(df), ok=True,
            period_from=period_from, period_to=period_to,
            metadata={"prev_from": prev_from, "prev_to": prev_to,
                      "unique_skus": df["sku_id"].nunique()},
        )

    @staticmethod
    def _load_bytes(filepath: Path) -> Optional[bytes]:
        """Load raw bytes from ZIP or direct XLSX."""
        try:
            if filepath.suffix.lower() == ".zip":
                with zipfile.ZipFile(filepath) as z:
                    # Find first xlsx inside
                    xlsx_files = [n for n in z.namelist()
                                  if n.lower().endswith((".xlsx",".xls")) and not n.startswith("__MACOSX")]
                    if not xlsx_files:
                        logger.error(f"[rating] No xlsx inside {filepath.name}")
                        return None
                    with z.open(xlsx_files[0]) as f:
                        return f.read()
            else:
                return filepath.read_bytes()
        except Exception as e:
            logger.error(f"[rating] _load_bytes failed: {e}")
            return None

    @staticmethod
    def _save_to_history(df: pd.DataFrame, period_from: str, period_to: str, source: str):
        """
        Save rating snapshot to historical archive.
        Key: "{period_from}_{period_to}"
        NEVER mixes data from different periods.
        """
        _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

        history: dict = {}
        if _HISTORY_PATH.exists():
            try:
                history = json.loads(_HISTORY_PATH.read_bytes())
            except Exception:
                history = {}

        period_key = f"{period_from}_{period_to}"
        records = json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))

        history[period_key] = {
            "period_from":  period_from,
            "period_to":    period_to,
            "source_file":  source,
            "loaded_at":    pd.Timestamp.now().isoformat(),
            "rows":         len(records),
            "records":      records,
        }

        _HISTORY_PATH.write_text(
            json.dumps(history, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        logger.info(f"[rating] Saved history snapshot: {period_key} ({len(records)} rows)")
