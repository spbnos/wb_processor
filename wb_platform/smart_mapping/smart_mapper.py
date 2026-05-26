"""
smart_mapper.py — главный класс SmartMapper.

Приоритет маппинга:
  1. KnowledgeEngine (wb_field_registry + термины оферты PDF)
  2. ColumnMatcher (wb_detailed_report + alias_dictionary)

Pipeline для каждой колонки:
  lookup → TypeDetector → LearningStore → ConfidenceScorer → решение
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from smart_mapping.column_matcher import ColumnMatcher
from smart_mapping.kb_integration import get_knowledge_engine
from smart_mapping.type_detector import detect_type, DataTypeResult
from smart_mapping.confidence_scorer import score as compute_score, ConfidenceLevel, ConfidenceResult
from smart_mapping.learning_store import LearningStore

logger = logging.getLogger(__name__)

# Минимальная уверенность KB, чтобы не падать в fuzzy
_KB_MIN_CONFIDENCE = 0.70


# ─── Структуры результата ────────────────────────────────────────────

@dataclass
class FieldDecision:
    """Решение по одной колонке."""
    source_column: str
    target_field: Optional[str]
    data_type: str
    date_format: Optional[str]
    confidence: ConfidenceResult
    is_ignored: bool = False
    needs_review: bool = False
    match_method: str = "unknown"
    runner_up_field: Optional[str] = None
    runner_up_score: float = 0.0


@dataclass
class SmartMappingResult:
    """Полный результат авто-маппинга файла."""
    struct_hash: str
    filepath: Path
    decisions: list[FieldDecision]

    auto_applied: list[FieldDecision] = field(default_factory=list)
    needs_review: list[FieldDecision] = field(default_factory=list)
    ignored: list[FieldDecision] = field(default_factory=list)

    total_columns: int = 0
    auto_count: int = 0
    review_count: int = 0
    ignored_count: int = 0
    avg_confidence: float = 0.0

    can_proceed: bool = True
    blocking_fields: list[str] = field(default_factory=list)


# ─── SmartMapper ─────────────────────────────────────────────────────

class SmartMapper:
    """
    Авто-интеллектуальная система маппинга колонок.

    Использование:
        mapper = SmartMapper()
        result = mapper.map_file(
            filepath=Path("wb_sales.xlsx"),
            struct_hash="abc123",
            sample_df=df.head(20),
        )
    """

    def __init__(
        self,
        use_db: bool = False,
        store_path: Optional[Path] = None,
        auto_threshold: float = 0.85,
        review_threshold: float = 0.60,
        use_kb: bool = True,
    ):
        self._matcher = ColumnMatcher()
        self._use_kb = use_kb
        self._kb = get_knowledge_engine() if use_kb else None
        self._store = LearningStore(
            use_db=use_db,
            path=store_path or LearningStore.__init__.__defaults__[1],
        )
        self._auto_threshold = auto_threshold
        self._review_threshold = review_threshold

    def map_file(
        self,
        filepath: Path,
        struct_hash: str,
        sample_df: pd.DataFrame,
    ) -> SmartMappingResult:
        logger.info(
            f"[smart_mapper] Mapping {len(sample_df.columns)} columns from "
            f"{filepath.name} (kb={'on' if self._use_kb else 'off'})"
        )

        decisions: list[FieldDecision] = []
        columns = list(sample_df.columns)

        for col in columns:
            decision = self._decide_column(
                source_column=col,
                struct_hash=struct_hash,
                sample_values=sample_df[col].dropna().tolist()[:50],
                columns_context=columns,
            )
            decisions.append(decision)
            logger.debug(
                f"[smart_mapper] {col!r} → {decision.target_field!r} "
                f"({decision.confidence.final_score:.3f} {decision.confidence.level.value})"
            )

        result = self._build_result(filepath, struct_hash, decisions)
        self._persist_decisions(struct_hash, result)

        logger.info(
            f"[smart_mapper] Done: {result.auto_count} auto, "
            f"{result.review_count} review, {result.ignored_count} ignored | "
            f"avg_conf={result.avg_confidence:.3f}"
        )
        return result

    def _decide_column(
        self,
        source_column: str,
        struct_hash: str,
        sample_values: list,
        columns_context: Optional[list[str]] = None,
    ) -> FieldDecision:
        type_result: DataTypeResult = detect_type(
            sample_values, column_name=source_column,
        )

        # ── L0: Knowledge Base (реестр WB + оферта) ───────────────────
        if self._use_kb and self._kb is not None:
            kb_hit = self._kb.lookup(source_column)
            if kb_hit and kb_hit.confidence >= _KB_MIN_CONFIDENCE:
                return self._decision_from_kb(
                    source_column, struct_hash, kb_hit, type_result,
                )

        # ── L1: ColumnMatcher (детализация + aliases) ───────────────
        return self._decision_from_matcher(
            source_column, struct_hash, type_result, columns_context,
        )

    def _decision_from_kb(
        self,
        source_column: str,
        struct_hash: str,
        kb_hit,
        type_result: DataTypeResult,
    ) -> FieldDecision:
        method = f"kb_{kb_hit.method}"
        data_type = kb_hit.data_type or type_result.detected_type
        date_format = kb_hit.date_format or type_result.format_hint

        # Служебные поля реестра — в extra через ignore в маппинге
        if not kb_hit.use_in_analytics:
            conf = compute_score(
                target_field="ignore",
                match_score=kb_hit.confidence,
                type_confidence=type_result.confidence,
                historical_hits=0,
            )
            return FieldDecision(
                source_column=source_column,
                target_field=None,
                data_type=data_type,
                date_format=date_format,
                confidence=conf,
                is_ignored=True,
                needs_review=False,
                match_method=method,
            )

        target = kb_hit.target_field
        hist_hits = self._store.get_hits(struct_hash, source_column, target)
        type_conf = 0.95 if data_type == type_result.detected_type else 0.88

        conf = compute_score(
            target_field=target,
            match_score=kb_hit.confidence,
            type_confidence=type_conf,
            historical_hits=hist_hits,
        )

        needs_review = conf.level in (
            ConfidenceLevel.NEEDS_REVIEW,
            ConfidenceLevel.LOW_CONF,
        )

        return FieldDecision(
            source_column=source_column,
            target_field=target,
            data_type=data_type,
            date_format=date_format,
            confidence=conf,
            is_ignored=False,
            needs_review=needs_review,
            match_method=method,
        )

    def _decision_from_matcher(
        self,
        source_column: str,
        struct_hash: str,
        type_result: DataTypeResult,
        columns_context: Optional[list[str]],
    ) -> FieldDecision:
        match_report = self._matcher.match(
            source_column,
            columns_context=columns_context or [],
        )

        if match_report.best and match_report.best.target_field == "ignore":
            conf = compute_score(
                target_field="ignore",
                match_score=1.0,
                type_confidence=type_result.confidence,
                historical_hits=0,
            )
            return FieldDecision(
                source_column=source_column,
                target_field=None,
                data_type=type_result.detected_type,
                date_format=type_result.format_hint,
                confidence=conf,
                is_ignored=True,
                needs_review=False,
                match_method=match_report.best.method,
            )

        if match_report.best is None:
            conf = compute_score(
                target_field="ignore",
                match_score=0.0,
                type_confidence=0.0,
                historical_hits=0,
            )
            return FieldDecision(
                source_column=source_column,
                target_field=None,
                data_type=type_result.detected_type,
                date_format=type_result.format_hint,
                confidence=conf,
                is_ignored=True,
                needs_review=False,
                match_method="no_match",
            )

        target = match_report.best.target_field
        hist_hits = self._store.get_hits(struct_hash, source_column, target)

        conf = compute_score(
            target_field=target,
            match_score=match_report.best.score,
            type_confidence=type_result.confidence,
            historical_hits=hist_hits,
        )

        needs_review = conf.level in (
            ConfidenceLevel.NEEDS_REVIEW,
            ConfidenceLevel.LOW_CONF,
        )
        is_ignored = conf.level == ConfidenceLevel.NO_MATCH

        return FieldDecision(
            source_column=source_column,
            target_field=target if not is_ignored else None,
            data_type=type_result.detected_type,
            date_format=type_result.format_hint,
            confidence=conf,
            is_ignored=is_ignored,
            needs_review=needs_review,
            match_method=match_report.best.method,
            runner_up_field=match_report.best.runner_up,
            runner_up_score=match_report.best.runner_up_score,
        )

    def _build_result(
        self,
        filepath: Path,
        struct_hash: str,
        decisions: list[FieldDecision],
    ) -> SmartMappingResult:
        auto_applied = [
            d for d in decisions
            if not d.is_ignored and not d.needs_review
        ]
        needs_review = [
            d for d in decisions
            if d.needs_review and not d.is_ignored
        ]
        ignored = [d for d in decisions if d.is_ignored]

        blocking = [
            d.source_column for d in needs_review
            if d.confidence.level == ConfidenceLevel.LOW_CONF
        ]

        scored = [d for d in decisions if not d.is_ignored]
        avg_conf = (
            sum(d.confidence.final_score for d in scored) / len(scored)
            if scored else 0.0
        )

        return SmartMappingResult(
            struct_hash=struct_hash,
            filepath=filepath,
            decisions=decisions,
            auto_applied=auto_applied,
            needs_review=needs_review,
            ignored=ignored,
            total_columns=len(decisions),
            auto_count=len(auto_applied),
            review_count=len(needs_review),
            ignored_count=len(ignored),
            avg_confidence=round(avg_conf, 4),
            can_proceed=len(blocking) == 0,
            blocking_fields=blocking,
        )

    def _persist_decisions(self, struct_hash: str, result: SmartMappingResult):
        for d in result.auto_applied:
            if d.target_field:
                self._store.record(
                    struct_hash=struct_hash,
                    source_column=d.source_column,
                    target_field=d.target_field,
                    score=d.confidence.final_score,
                    confirmed=False,
                )

    def confirm_decision(
        self,
        struct_hash: str,
        source_column: str,
        approved_field: str,
    ):
        self._store.confirm(struct_hash, source_column)
        logger.info(f"[smart_mapper] Confirmed: {source_column!r} → {approved_field!r}")

    def reject_decision(
        self,
        struct_hash: str,
        source_column: str,
        correct_field: str,
    ):
        self._store.reject(struct_hash, source_column, correct_field, score=1.0)
        logger.info(f"[smart_mapper] Corrected: {source_column!r} → {correct_field!r}")
