"""
confidence_scorer.py — итоговый confidence score для одного поля.

Входы:
    - match_score    : ColumnMatcher score (0..1)
    - type_confidence: TypeDetector confidence (0..1)
    - historical_hits: сколько раз это решение уже применялось (0+)
    - is_required    : маппинг обязательный?

Формула:
    base = 0.65 * match_score + 0.25 * type_confidence + 0.10 * history_bonus
    final = clamp(base * required_multiplier, 0, 1)

Thresholds:
    >= 0.85  AUTO_APPLY   — применить без подтверждения
    >= 0.60  NEEDS_REVIEW — применить, пометить для UI review
    <  0.60  LOW_CONF     — показать UI для ручного подтверждения
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import math


class ConfidenceLevel(Enum):
    AUTO_APPLY   = "auto_apply"    # >= 0.85
    NEEDS_REVIEW = "needs_review"  # 0.60 – 0.84
    LOW_CONF     = "low_conf"      # < 0.60
    NO_MATCH     = "no_match"      # score == 0


_THRESHOLDS = {
    ConfidenceLevel.AUTO_APPLY:   0.85,
    ConfidenceLevel.NEEDS_REVIEW: 0.60,
}


@dataclass
class ConfidenceResult:
    target_field: str
    final_score: float
    level: ConfidenceLevel
    match_score: float
    type_confidence: float
    history_bonus: float
    explanation: str


def _history_bonus(hits: int) -> float:
    """Логарифмический бонус за историю применений. Max = 0.15."""
    if hits <= 0:
        return 0.0
    return min(0.15, 0.05 * math.log1p(hits))


def _level(score: float) -> ConfidenceLevel:
    if score == 0.0:
        return ConfidenceLevel.NO_MATCH
    if score >= _THRESHOLDS[ConfidenceLevel.AUTO_APPLY]:
        return ConfidenceLevel.AUTO_APPLY
    if score >= _THRESHOLDS[ConfidenceLevel.NEEDS_REVIEW]:
        return ConfidenceLevel.NEEDS_REVIEW
    return ConfidenceLevel.LOW_CONF


def score(
    target_field: str,
    match_score: float,
    type_confidence: float = 1.0,
    historical_hits: int = 0,
    is_required: bool = False,
) -> ConfidenceResult:
    """
    Вычисляет итоговый confidence для одного поля.

    Args:
        target_field:     предполагаемое целевое поле
        match_score:      score из ColumnMatcher (0..1)
        type_confidence:  score из TypeDetector (0..1)
        historical_hits:  кол-во раз поле применялось ранее
        is_required:      если обязательное и низкий confidence → не AUTO_APPLY

    Returns:
        ConfidenceResult
    """
    hb = _history_bonus(historical_hits)

    base = (
        0.65 * match_score
        + 0.25 * type_confidence
        + 0.10 * (hb / 0.15)   # нормализуем hb к диапазону 0..1
    )
    base = max(0.0, min(1.0, base))

    # Если required и confidence < 0.75 — понижаем до NEEDS_REVIEW
    if is_required and base >= _THRESHOLDS[ConfidenceLevel.AUTO_APPLY] and base < 0.90:
        base = min(base, 0.84)

    lvl = _level(base)

    explanation_parts = [
        f"match={match_score:.2f}",
        f"type={type_confidence:.2f}",
        f"history_bonus={hb:.3f}(n={historical_hits})",
    ]
    if is_required:
        explanation_parts.append("required=true")

    return ConfidenceResult(
        target_field=target_field,
        final_score=round(base, 4),
        level=lvl,
        match_score=round(match_score, 4),
        type_confidence=round(type_confidence, 4),
        history_bonus=round(hb, 4),
        explanation=" | ".join(explanation_parts),
    )


def score_batch(
    decisions: list[dict],
) -> list[ConfidenceResult]:
    """
    decisions: список словарей с ключами:
        target_field, match_score, type_confidence, historical_hits, is_required
    """
    return [score(**d) for d in decisions]
