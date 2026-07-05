"""标签冲突人工审核输入与候选模型。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from .enums import LabelStatus, ReviewStatus
from .paths import reject_symlink_chain
from .role_resolution import CoreRoleResolution
from .schema_registry import SCHEMA_REGISTRY
from .validation import read_and_validate_csv, validate_rows


def load_manual_reviews(
    root: Path, resolutions: Iterable[CoreRoleResolution]
) -> dict[tuple[str, str], dict[str, Any]]:
    conflicts = {
        (item.compound_id, item.dataset_role.value)
        for item in resolutions
        if item.label_status is LabelStatus.CONFLICT
    }
    path = root / "data" / "manual" / "modeling_conflict_decisions.csv"
    if not path.exists():
        return {}
    reject_symlink_chain(root, path)
    if not path.is_file():
        raise ValueError("人工冲突路径存在但不是普通文件")
    rows = read_and_validate_csv(path, SCHEMA_REGISTRY["modeling/conflict_reviews.csv"])
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["compound_id"], row["dataset_role"])
        if key not in conflicts:
            raise ValueError(f"人工审核引用未知或非 conflict 对象：{key!r}")
        if row["review_reason"] == "" or row["reviewer"] == "":
            raise ValueError(f"人工审核理由和审核人不允许为空：{key!r}")
        result[key] = row
    return result


def apply_manual_reviews(
    resolutions: Iterable[CoreRoleResolution],
    decisions: dict[tuple[str, str], dict[str, Any]],
) -> list[CoreRoleResolution]:
    result: list[CoreRoleResolution] = []
    for item in resolutions:
        key = (item.compound_id, item.dataset_role.value)
        if key in decisions:
            result.append(replace(item, review_status=ReviewStatus.CONFIRMED_EXCLUDE))
        else:
            result.append(item)
    return result


def build_review_candidates(
    resolutions: Iterable[CoreRoleResolution],
    decisions: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in resolutions:
        if item.label_status is not LabelStatus.CONFLICT:
            continue
        key = (item.compound_id, item.dataset_role.value)
        decision = decisions.get(key)
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
                "decision": None if decision is None else decision["decision"],
                "review_reason": None
                if decision is None
                else decision["review_reason"],
                "reviewer": None if decision is None else decision["reviewer"],
                "reviewed_at_utc": None
                if decision is None
                else decision["reviewed_at_utc"],
            }
        )
    validate_rows(
        rows, SCHEMA_REGISTRY["reports/modeling_conflict_review_candidates.csv"]
    )
    return rows
