"""
mapping_bridge.py — конвертер между SmartMapper и MappingStorage.

SmartMappingResult → MappingConfig → MappingStorage.save()

Это центральный адаптер: знает форматы обеих сторон.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

# SmartMapper живёт в wb_platform, добавляем в path
_PLATFORM_DIR = Path(__file__).resolve().parents[1] / "wb_platform"
if str(_PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(_PLATFORM_DIR))

from smart_mapping.smart_mapper import SmartMappingResult, FieldDecision
from smart_mapping.confidence_scorer import ConfidenceLevel
from mapping.interactive_mapper import MappingConfig, FieldMapping
from mapping.mapping_storage import MappingStorage
from review_queue.queue_store import ReviewQueue, ReviewItem

logger = logging.getLogger(__name__)


def smart_result_to_config(
    result: SmartMappingResult,
    name: str,
    category: str = "external",
    subcategory: str = "custom",
    purpose: str = "analytics",
) -> MappingConfig:
    """
    Конвертирует SmartMappingResult в MappingConfig для сохранения в MappingStorage.

    В активный маппинг попадают только AUTO_APPLY поля.
    NEEDS_REVIEW / LOW_CONF → ignore до подтверждения в review (CLI/Dashboard).
    """
    auto_ids = {id(d) for d in result.auto_applied}
    fields: list[FieldMapping] = []

    for decision in result.decisions:
        if (
            decision.is_ignored
            or decision.target_field is None
            or id(decision) not in auto_ids
        ):
            fields.append(FieldMapping(
                source_column=decision.source_column,
                target_field="ignore",
                data_type="str",
            ))
            continue

        fields.append(FieldMapping(
            source_column=decision.source_column,
            target_field=decision.target_field,
            data_type=decision.data_type,
            date_format=decision.date_format,
            is_required=False,
            description=f"auto:{getattr(decision, 'match_method', 'unknown')}@{decision.confidence.final_score:.2f}",
        ))

    return MappingConfig(
        name=name,
        struct_hash=result.struct_hash,
        category=category,
        subcategory=subcategory,
        purpose=purpose,
        raw_columns=[d.source_column for d in result.decisions],
        column_count=result.total_columns,
        fields=fields,
    )


def build_review_items(
    result: SmartMappingResult,
    filepath: Path,
    sample_values: dict[str, list],
) -> list[ReviewItem]:
    """
    Создаёт ReviewItem для каждого решения требующего подтверждения.

    sample_values: {source_column: [val1, val2, ...]}
    """
    items: list[ReviewItem] = []

    for decision in result.needs_review:
        item_id = f"{result.struct_hash}::{decision.source_column}"
        conf = decision.confidence

        item = ReviewItem(
            id=item_id,
            struct_hash=result.struct_hash,
            source_column=decision.source_column,
            suggested_field=decision.target_field,
            suggested_type=decision.data_type,
            confidence_score=conf.final_score,
            confidence_level=conf.level.value,
            match_method=getattr(decision, "match_method", "unknown"),
            runner_up_field=getattr(decision, "runner_up_field", None),
            runner_up_score=getattr(decision, "runner_up_score", 0.0),
            filepath=str(filepath),
            filename=filepath.name,
            sample_values=sample_values.get(decision.source_column, [])[:5],
        )
        items.append(item)

    return items


def apply_review_decisions(
    struct_hash: str,
    queue: ReviewQueue,
    storage: MappingStorage,
) -> int:
    """
    После того как пользователь подтвердил items в очереди —
    обновляет MappingStorage с правильными полями.

    Возвращает кол-во обновлённых полей.
    """
    approved = [
        i for i in queue.get_all(status="approved")
        if i.struct_hash == struct_hash
    ]
    rejected = [
        i for i in queue.get_all(status="rejected")
        if i.struct_hash == struct_hash
    ]
    resolved = approved + rejected

    if not resolved:
        return 0

    # Получаем текущий маппинг
    mapping = storage.find_by_struct_hash(struct_hash)
    if not mapping:
        logger.warning(f"[bridge] No mapping found for hash={struct_hash}")
        return 0

    # Строим dict исправлений: source_column → correct_field
    corrections: dict[str, str] = {}
    for item in resolved:
        if item.correct_field:
            corrections[item.source_column] = item.correct_field

    if not corrections:
        return 0

    # Обновляем поля маппинга
    from mapping.mapping_storage import MappingFieldObj
    updated_fields = []
    for f in mapping.fields:
        if f.source_column in corrections:
            new_target = corrections[f.source_column]
            updated_fields.append(FieldMapping(
                source_column=f.source_column,
                target_field=new_target,
                data_type=f.data_type,
                date_format=f.date_format,
                is_required=f.is_required,
                description=f"confirmed_by_user",
            ))
        else:
            updated_fields.append(FieldMapping(
                source_column=f.source_column,
                target_field=f.target_field,
                data_type=f.data_type,
                date_format=f.date_format,
                is_required=f.is_required,
            ))

    storage.update(mapping.id, fields=updated_fields)
    logger.info(f"[bridge] Applied {len(corrections)} review corrections to mapping id={mapping.id}")

    # Очищаем resolved items
    queue.expire_for_hash(struct_hash)

    return len(corrections)
