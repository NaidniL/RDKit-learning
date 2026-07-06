"""将标签、结构、泄漏和人工审核状态收敛为最终角色行。"""

from __future__ import annotations

from typing import Any, Iterable

from .enums import (
    DatasetRole,
    LabelStatus,
    LeakageStatus,
    ResolutionRule,
    ReviewStatus,
    StructureStatus,
)
from .fingerprint import CLEANING_RUN_ID
from .leakage import LeakageBuild
from .role_resolution import CoreRoleResolution
from .schema_registry import SCHEMA_REGISTRY
from .serialization import canonical_json
from .validation import expected_split_eligibility, validate_rows


def _rules(item: CoreRoleResolution, leakage: LeakageStatus, tautomer: bool) -> list[str]:
    result: set[str] = set()
    if item.label_status is LabelStatus.CLEAR_POSITIVE:
        result.add(ResolutionRule.UNANIMOUS_CLEAR_POSITIVE.value)
    elif item.label_status is LabelStatus.CLEAR_NEGATIVE:
        result.add(ResolutionRule.UNANIMOUS_CLEAR_NEGATIVE.value)
    elif item.label_status is LabelStatus.UNCERTAIN:
        result.add(ResolutionRule.NO_CLEAR_BINARY_LABEL.value)
    elif item.review_status is ReviewStatus.CONFIRMED_EXCLUDE:
        result.add(ResolutionRule.CONFIRMED_EXACT_LABEL_CONFLICT_EXCLUDE.value)
    if item.structure_status == StructureStatus.INELIGIBLE.value:
        result.add(ResolutionRule.STRUCTURE_INELIGIBLE.value)
    if leakage is LeakageStatus.EXACT_OVERLAP:
        result.add(ResolutionRule.EXTERNAL_EXACT_LEAKAGE.value)
    elif leakage is LeakageStatus.CONNECTIVITY_OVERLAP:
        result.add(ResolutionRule.EXTERNAL_CONNECTIVITY_LEAKAGE.value)
    if tautomer:
        result.add(ResolutionRule.EXTERNAL_TAUTOMER_OVERLAP_REPORTED.value)
    return sorted(result, key=canonical_json)


def _exclusion_reasons(
    item: CoreRoleResolution, leakage: LeakageStatus
) -> list[str]:
    reasons = set(item.structure_reasons)
    if item.label_status is LabelStatus.CONFLICT:
        reasons.add("label_conflict")
    elif item.label_status is LabelStatus.UNCERTAIN:
        reasons.add("label_uncertain")
    if leakage is LeakageStatus.EXACT_OVERLAP:
        reasons.add("external_exact_overlap")
    elif leakage is LeakageStatus.CONNECTIVITY_OVERLAP:
        reasons.add("external_connectivity_overlap")
    return sorted(reasons, key=canonical_json)


def finalize_role_resolutions(
    resolutions: Iterable[CoreRoleResolution], leakage: LeakageBuild
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """生成最终角色表与完整 compound-level 排除表。"""

    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for item in resolutions:
        key = (item.compound_id, item.dataset_role.value)
        leakage_status = leakage.role_statuses[key]
        has_tautomer = (
            item.dataset_role is DatasetRole.EXTERNAL
            and item.compound_id in leakage.tautomer_overlap_ids
        )
        structure_status = StructureStatus(item.structure_status)
        split_eligibility = expected_split_eligibility(
            item.dataset_role,
            item.label_status,
            structure_status,
            leakage_status,
        )
        reasons = _exclusion_reasons(item, leakage_status)
        row = {
            "compound_id": item.compound_id,
            "dataset_role": item.dataset_role.value,
            "role_normalized_label": item.role_normalized_label,
            "label_status": item.label_status.value,
            "review_status": item.review_status.value,
            "label_resolution_record_keys_json": list(item.resolution_keys),
            "nonresolution_record_keys_json": list(item.nonresolution_keys),
            "label_resolution_sources_json": list(item.resolution_sources),
            "discordant_nonclear_count": item.discordant_nonclear_count,
            "has_discordant_nonclear_evidence": item.has_discordant_nonclear_evidence,
            "structure_status": structure_status.value,
            "leakage_status": leakage_status.value,
            "has_tautomer_overlap": has_tautomer,
            "split_eligibility": split_eligibility.value,
            "exclusion_reasons_json": reasons,
            "resolution_rules_json": _rules(item, leakage_status, has_tautomer),
            "cleaning_run_id": CLEANING_RUN_ID,
        }
        rows.append(row)
        exclusions.extend(
            {
                "compound_id": item.compound_id,
                "dataset_role": item.dataset_role.value,
                "exclusion_reason": reason,
            }
            for reason in reasons
        )
    rows.sort(key=lambda row: (row["compound_id"], row["dataset_role"]))
    exclusions.sort(
        key=lambda row: (
            row["compound_id"],
            row["dataset_role"],
            row["exclusion_reason"],
        )
    )
    validate_rows(rows, SCHEMA_REGISTRY["modeling/compound_role_resolutions.csv"])
    validate_rows(exclusions, SCHEMA_REGISTRY["modeling/compound_exclusions.csv"])
    expected = {
        (row["compound_id"], row["dataset_role"], reason)
        for row in rows
        for reason in row["exclusion_reasons_json"]
    }
    actual = {
        (row["compound_id"], row["dataset_role"], row["exclusion_reason"])
        for row in exclusions
    }
    if actual != expected or len(exclusions) != len(actual):
        raise AssertionError("compound exclusions 与最终角色原因未双向对齐")
    return rows, exclusions
