"""标签冲突的确定性计数裁决与审计候选表。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from .enums import LabelStatus, ReviewDecision, ReviewStatus
from .role_resolution import CoreRoleResolution
from .schema_registry import SCHEMA_REGISTRY
from .validation import validate_rows


def conflict_decision(item: CoreRoleResolution) -> tuple[ReviewDecision, str, int | None]:
    """按冻结的三步计数规则裁决一条确定性标签冲突。"""

    positive = item.clear_positive_count
    negative = item.clear_negative_count
    if positive <= 0 or negative <= 0:
        raise ValueError("计数裁决要求同时存在明确阳性和明确阴性记录")
    total = positive + negative
    if total <= 10:
        return (
            ReviewDecision.EXCLUDE_TOTAL_COUNT_LE_10,
            "明确阳性与明确阴性记录总数不超过 10，按规则排除",
            None,
        )
    if abs(positive - negative) <= 10:
        return (
            ReviewDecision.EXCLUDE_COUNT_MARGIN_LE_10,
            "明确阳性与明确阴性记录数差绝对值不超过 10，按规则排除",
            None,
        )
    if positive > negative:
        return (
            ReviewDecision.ASSIGN_POSITIVE,
            "明确阳性记录数更多且差值大于 10，按规则标记为阳性",
            1,
        )
    return (
        ReviewDecision.ASSIGN_NEGATIVE,
        "明确阴性记录数更多且差值大于 10，按规则标记为阴性",
        0,
    )


def apply_conflict_resolution(
    resolutions: Iterable[CoreRoleResolution],
) -> list[CoreRoleResolution]:
    """将通过计数门槛的冲突转为可追溯的二分类标签。"""

    result: list[CoreRoleResolution] = []
    for item in resolutions:
        if item.label_status is not LabelStatus.CONFLICT:
            result.append(item)
            continue
        decision, _, label = conflict_decision(item)
        if decision is ReviewDecision.ASSIGN_POSITIVE:
            result.append(
                replace(
                    item,
                    role_normalized_label=label,
                    label_status=LabelStatus.CLEAR_POSITIVE,
                    review_status=ReviewStatus.AUTOMATIC_RESOLVED,
                )
            )
        elif decision is ReviewDecision.ASSIGN_NEGATIVE:
            result.append(
                replace(
                    item,
                    role_normalized_label=label,
                    label_status=LabelStatus.CLEAR_NEGATIVE,
                    review_status=ReviewStatus.AUTOMATIC_RESOLVED,
                )
            )
        else:
            result.append(replace(item, review_status=ReviewStatus.AUTOMATIC_EXCLUDE))
    return result


def build_review_candidates(
    resolutions: Iterable[CoreRoleResolution],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in resolutions:
        if not (
            item.review_status is ReviewStatus.AUTOMATIC_EXCLUDE
            or item.review_status is ReviewStatus.AUTOMATIC_RESOLVED
        ):
            continue
        decision, reason, label = conflict_decision(item)
        rows.append(
            {
                "compound_id": item.compound_id,
                "dataset_role": item.dataset_role.value,
                "clear_positive_count": item.clear_positive_count,
                "clear_negative_count": item.clear_negative_count,
                "record_keys_json": sorted(
                    item.resolution_keys + item.nonresolution_keys
                ),
                "review_status": item.review_status.value,
                "decision": decision.value,
                "resolved_label": label,
                "resolution_reason": reason,
            }
        )
    validate_rows(
        rows, SCHEMA_REGISTRY["reports/modeling_conflict_review_candidates.csv"]
    )
    return rows
