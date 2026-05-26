"""
column_matcher.py — многоуровневый алгоритм сопоставления колонок.

Уровни (применяются последовательно, берём max score):

    L1  Exact match         — нормализованная строка совпадает точно
    L2  Alias match         — точное вхождение в alias dictionary
    L3  Substring match     — колонка содержится в alias или alias в колонке
    L4  Fuzzy token sort    — rapidfuzz.token_sort_ratio
    L5  Fuzzy partial       — rapidfuzz.partial_ratio
    L6  Word overlap        — доля совпадающих слов

Результат: MatchResult с итоговым score 0.0–1.0 и методом-победителем.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz
from rapidfuzz.process import extractOne

from smart_mapping.alias_dictionary import ALIASES, REVERSE_LOOKUP, ALL_TARGET_FIELDS

# Слабый fuzzy ниже этого порога не предлагается (anti-guess)
WEAK_MATCH_MAX_SCORE = 0.55
_TRUSTED_METHODS = frozenset({
    "wb_exact", "wb_ignore", "exact", "alias_exact",
})


# ─── Веса по уровням ────────────────────────────────────────────────
_LEVEL_WEIGHTS = {
    "exact":     1.00,
    "alias_exact": 0.97,
    "alias_substring": 0.88,
    "fuzzy_token": None,   # нормализуется из 100 → float
    "fuzzy_partial": None,
    "word_overlap": None,
}

# Порог ниже которого поле не предлагается
_MIN_SCORE = 0.35


@dataclass
class MatchResult:
    target_field: str
    score: float            # 0.0 – 1.0
    method: str             # какой уровень дал победу
    runner_up: Optional[str] = None        # второй кандидат
    runner_up_score: float = 0.0


@dataclass
class ColumnMatchReport:
    """Полный отчёт по одной колонке файла."""
    source_column: str
    normalized: str
    best: Optional[MatchResult]
    all_candidates: list[MatchResult] = field(default_factory=list)


# ─── Нормализация ────────────────────────────────────────────────────
_RE_SPACES = re.compile(r"[\s\-_/\\.,;:]+")
_RE_NONALPHA = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str) -> str:
    """Нормализует текст колонки для сравнения."""
    t = str(text).lower().strip()
    t = _RE_NONALPHA.sub(" ", t)
    t = _RE_SPACES.sub(" ", t).strip()
    return t


def _words(text: str) -> set[str]:
    return set(w for w in text.split() if len(w) > 1)


# ─── Уровни матчинга ────────────────────────────────────────────────

def _l0_wb_detailed(norm_col: str, raw_column: str = "") -> Optional[MatchResult]:
    """L0: официальный словарь колонок детализации WB."""
    from smart_mapping.wb_detailed_report import match_wb_column

    return match_wb_column(raw_column or norm_col)


def _l1_exact(norm_col: str) -> Optional[MatchResult]:
    """L1: точное совпадение с target_field именем."""
    if norm_col in ALL_TARGET_FIELDS:
        return MatchResult(target_field=norm_col, score=1.0, method="exact")
    return None


def _l2_alias_exact(norm_col: str) -> Optional[MatchResult]:
    """L2: точное совпадение с алиасом."""
    if norm_col in REVERSE_LOOKUP:
        return MatchResult(
            target_field=REVERSE_LOOKUP[norm_col],
            score=0.97,
            method="alias_exact",
        )
    return None


def _l3_alias_substring(norm_col: str) -> Optional[MatchResult]:
    """L3: алиас содержится в колонке или колонка в алиасе."""
    best_field: Optional[str] = None
    best_score = 0.0

    for alias, field_name in REVERSE_LOOKUP.items():
        # Колонка содержит алиас
        if alias in norm_col:
            # Чем короче алиас относительно колонки — тем меньше уверенность
            ratio = len(alias) / max(len(norm_col), 1)
            score = 0.88 * (0.5 + 0.5 * ratio)
            if score > best_score:
                best_score = score
                best_field = field_name
        # Алиас содержит колонку
        elif norm_col in alias and len(norm_col) >= 3:
            ratio = len(norm_col) / max(len(alias), 1)
            score = 0.82 * (0.5 + 0.5 * ratio)
            if score > best_score:
                best_score = score
                best_field = field_name

    if best_field and best_score >= _MIN_SCORE:
        return MatchResult(
            target_field=best_field,
            score=round(best_score, 4),
            method="alias_substring",
        )
    return None


def _l4_fuzzy_token(norm_col: str) -> Optional[MatchResult]:
    """L4: rapidfuzz token_sort_ratio по всем алиасам."""
    # Собираем плоский список (alias, field_name)
    alias_list = [(alias, field_name) for alias, field_name in REVERSE_LOOKUP.items()]
    if not alias_list:
        return None

    best_score_raw = 0
    best_field: Optional[str] = None

    for alias, field_name in alias_list:
        s = fuzz.token_sort_ratio(norm_col, alias)
        if s > best_score_raw:
            best_score_raw = s
            best_field = field_name

    if best_field and best_score_raw >= 55:
        score = round(best_score_raw / 100 * 0.82, 4)
        return MatchResult(
            target_field=best_field,
            score=score,
            method="fuzzy_token",
        )
    return None


def _l5_fuzzy_partial(norm_col: str) -> Optional[MatchResult]:
    """L5: rapidfuzz partial_ratio."""
    best_score_raw = 0
    best_field: Optional[str] = None

    for alias, field_name in REVERSE_LOOKUP.items():
        s = fuzz.partial_ratio(norm_col, alias)
        if s > best_score_raw:
            best_score_raw = s
            best_field = field_name

    if best_field and best_score_raw >= 70:
        score = round(best_score_raw / 100 * 0.72, 4)
        return MatchResult(
            target_field=best_field,
            score=score,
            method="fuzzy_partial",
        )
    return None


def _l6_word_overlap(norm_col: str) -> Optional[MatchResult]:
    """L6: доля совпадающих слов."""
    col_words = _words(norm_col)
    if not col_words:
        return None

    best_score = 0.0
    best_field: Optional[str] = None

    for field_name, aliases in ALIASES.items():
        for alias in aliases:
            alias_words = _words(alias)
            if not alias_words:
                continue
            intersection = col_words & alias_words
            if intersection:
                # Jaccard-подобная мера
                union = col_words | alias_words
                score = len(intersection) / len(union) * 0.70
                if score > best_score:
                    best_score = score
                    best_field = field_name

    if best_field and best_score >= _MIN_SCORE:
        return MatchResult(
            target_field=best_field,
            score=round(best_score, 4),
            method="word_overlap",
        )
    return None


# ─── Главный matcher ─────────────────────────────────────────────────

class ColumnMatcher:
    """
    Сопоставляет одну колонку со всеми target_fields.

    Использование:
        matcher = ColumnMatcher()
        report = matcher.match("Артикул WB")
        print(report.best.target_field, report.best.score)
    """

    def __init__(self, min_score: float = _MIN_SCORE, use_wb_dictionary: bool = True):
        self._min_score = min_score
        self._use_wb_dictionary = use_wb_dictionary
        self._levels = [
            _l1_exact,
            _l2_alias_exact,
            _l3_alias_substring,
            _l4_fuzzy_token,
            _l5_fuzzy_partial,
            _l6_word_overlap,
        ]

    def match(self, column: str, columns_context: Optional[list[str]] = None) -> ColumnMatchReport:
        norm = normalize(column)
        results: list[MatchResult] = []

        # L0 — словарь WB (включается если файл похож на детализацию)
        ctx = columns_context or []
        if self._use_wb_dictionary:
            from smart_mapping.wb_detailed_report import is_wb_detailed_columns

            if is_wb_detailed_columns(ctx) or is_wb_detailed_columns([column]):
                r0 = _l0_wb_detailed(norm, column)
                if r0:
                    results.append(r0)

        for level_fn in self._levels:
            r = level_fn(norm)
            if r and r.score >= self._min_score:
                results.append(r)

        if not results:
            return ColumnMatchReport(
                source_column=column,
                normalized=norm,
                best=None,
            )

        # Группируем по target_field — берём max score для каждого поля
        by_field: dict[str, MatchResult] = {}
        for r in results:
            if r.target_field not in by_field or r.score > by_field[r.target_field].score:
                by_field[r.target_field] = r

        sorted_results = sorted(by_field.values(), key=lambda x: x.score, reverse=True)
        best = sorted_results[0]

        # Не угадывать: слабый fuzzy → нет совпадения
        if best.method not in _TRUSTED_METHODS and best.score < WEAK_MATCH_MAX_SCORE:
            return ColumnMatchReport(
                source_column=column,
                normalized=norm,
                best=None,
            )

        if len(sorted_results) > 1:
            best.runner_up = sorted_results[1].target_field
            best.runner_up_score = sorted_results[1].score

        return ColumnMatchReport(
            source_column=column,
            normalized=norm,
            best=best,
            all_candidates=sorted_results,
        )

    def match_many(self, columns: list[str]) -> list[ColumnMatchReport]:
        return [self.match(col, columns_context=columns) for col in columns]
