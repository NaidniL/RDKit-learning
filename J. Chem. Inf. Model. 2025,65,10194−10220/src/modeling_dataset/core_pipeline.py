"""实现批次 3 的纯内存核心重建与泄漏状态收敛。"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .compounds import CompoundBuild, build_compounds
from .duplicate_groups import build_duplicate_groups
from .enums import DatasetRole, LabelStatus, LeakageStatus, SplitEligibility
from .fingerprint import input_fingerprint
from .leakage import LeakageBuild, build_leakage
from .manual_reviews import (
    apply_manual_reviews,
    build_review_candidates,
    load_manual_reviews,
)
from .record_exclusions import build_record_exclusions
from .role_finalization import finalize_role_resolutions
from .role_resolution import CoreRoleResolution, build_core_role_resolutions
from .source_records import load_records_all
from .schema_registry import SCHEMA_REGISTRY
from .validation import validate_rows


EXTRA_ORTHOGONAL_CONFLICT = (
    "CMP:VZUNGTLZRAYYDE-UHFFFAOYSA-N",
    "development",
)


@dataclass(frozen=True)
class CoreBuild:
    records_all: list[dict[str, Any]]
    record_exclusions: list[dict[str, Any]]
    compounds: list[dict[str, Any]]
    fingerprints: dict[str, Any]
    role_resolutions: list[CoreRoleResolution]
    finalized_role_resolutions: list[dict[str, Any]]
    compound_exclusions: list[dict[str, Any]]
    duplicate_groups: list[dict[str, Any]]
    review_candidates: list[dict[str, Any]]
    leakage: LeakageBuild
    summary: dict[str, Any]


def _read_view(root: Path, filename: str) -> list[dict[str, str]]:
    path = root / "data" / "processed" / filename
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, strict=True)]


def _view_keys(
    rows: Iterable[Mapping[str, str]],
) -> set[tuple[str, str]]:
    return {
        (f"CMP:{row['standard_inchikey']}", row["dataset_role"])
        for row in rows
    }


def _view_labels(
    rows: Iterable[Mapping[str, str]],
) -> dict[tuple[str, str], int]:
    result: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (f"CMP:{row['standard_inchikey']}", row["dataset_role"])
        if row["label_binary"] not in {"0", "1"}:
            raise ValueError(f"冻结主集标签非法：{key!r}")
        result[key] = int(row["label_binary"])
    return result


def _resolution_map(
    resolutions: Iterable[CoreRoleResolution],
) -> dict[tuple[str, str], CoreRoleResolution]:
    return {
        (item.compound_id, item.dataset_role.value): item for item in resolutions
    }


def _assert_frozen_views(
    root: Path,
    compounds: Iterable[Mapping[str, Any]],
    resolutions: list[CoreRoleResolution],
) -> None:
    resolution_map = _resolution_map(resolutions)
    eligible_conflicts = {
        key
        for key, item in resolution_map.items()
        if item.label_status is LabelStatus.CONFLICT
        and item.structure_status == "eligible"
    }
    frozen_conflicts = _view_keys(_read_view(root, "conflict_set.csv"))
    if eligible_conflicts != frozen_conflicts:
        raise ValueError(
            "重建的 structure-eligible conflict 与冻结视图不一致；"
            f"缺少={sorted(frozen_conflicts - eligible_conflicts)}，"
            f"新增={sorted(eligible_conflicts - frozen_conflicts)}"
        )
    all_conflicts = {
        key for key, item in resolution_map.items() if item.label_status is LabelStatus.CONFLICT
    }
    if len(all_conflicts) != 614:
        raise ValueError(f"标签冲突总数应为 614，实际为 {len(all_conflicts)}")
    if all_conflicts - eligible_conflicts != {EXTRA_ORTHOGONAL_CONFLICT}:
        raise ValueError("被结构优先级遮蔽的正交标签冲突不一致")
    extra = resolution_map[EXTRA_ORTHOGONAL_CONFLICT]
    if extra.structure_status != "ineligible" or (
        "structure_representation_conflict" not in extra.structure_reasons
    ):
        raise ValueError("已知正交冲突缺少结构排除状态")
    eligible_uncertain = {
        key
        for key, item in resolution_map.items()
        if item.label_status is LabelStatus.UNCERTAIN
        and item.structure_status == "eligible"
        and not item.endpoint_only
    }
    frozen_uncertain = _view_keys(_read_view(root, "uncertain_set.csv"))
    if eligible_uncertain != frozen_uncertain:
        raise ValueError("重建 uncertain 集合与冻结视图不一致")
    development = _view_labels(_read_view(root, "development_pool.csv"))
    for key, label in development.items():
        item = resolution_map.get(key)
        if item is None or item.role_normalized_label != label:
            raise ValueError(f"development pool 成员或标签不一致：{key!r}")
        if item.structure_status != "eligible":
            raise ValueError(f"development pool 包含结构不合格对象：{key!r}")
    rebuilt_development = {
        key: item.role_normalized_label
        for key, item in resolution_map.items()
        if item.dataset_role is DatasetRole.DEVELOPMENT
        and item.structure_status == "eligible"
        and item.label_status
        in {LabelStatus.CLEAR_POSITIVE, LabelStatus.CLEAR_NEGATIVE}
    }
    if rebuilt_development != development:
        raise ValueError("development pool 的键和标签未精确复现")
    external = _view_labels(_read_view(root, "external_ccris_test.csv"))
    for key, label in external.items():
        item = resolution_map.get(key)
        if item is None or item.role_normalized_label != label:
            raise ValueError(f"primary external 成员或标签不一致：{key!r}")
        if item.structure_status != "eligible":
            raise ValueError(f"primary external 包含结构不合格对象：{key!r}")
    structure_conflicts = {
        str(row["compound_id"])
        for row in compounds
        if "structure_representation_conflict" in row["structure_reasons_json"]
    }
    frozen_structure_conflicts = {
        f"CMP:{row['standard_inchikey']}"
        for row in _read_view(root, "structure_representation_conflict.csv")
    }
    if structure_conflicts != frozen_structure_conflicts or len(structure_conflicts) != 4:
        raise ValueError("已知结构表示冲突集合不一致")


def _summary(
    records: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
    compounds: list[dict[str, Any]],
    resolutions: list[CoreRoleResolution],
    duplicate_groups: list[dict[str, Any]],
    finalized: list[dict[str, Any]],
    compound_exclusions: list[dict[str, Any]],
    leakage: LeakageBuild,
    decisions: dict[tuple[str, str], dict[str, Any]],
    fingerprint: str,
) -> dict[str, Any]:
    label_counts = Counter(item.label_status.value for item in resolutions)
    role_counts = Counter(item.dataset_role.value for item in resolutions)
    structure_counts = Counter(str(row["structure_status"]) for row in compounds)
    duplicate_counts = Counter(str(row["exact_duplicate_class"]) for row in duplicate_groups)
    conflict_count = label_counts[LabelStatus.CONFLICT.value]
    leakage_counts = Counter(str(row["leakage_status"]) for row in finalized)
    eligibility_counts = Counter(str(row["split_eligibility"]) for row in finalized)
    return {
        "input_fingerprint": fingerprint,
        "records_all": len(records),
        "records_with_standardized_key": sum(
            record["standard_inchikey"] != "" for record in records
        ),
        "records_without_standardized_key": sum(
            record["standard_inchikey"] == "" for record in records
        ),
        "compound_count": len(compounds),
        "development_role_count": role_counts[DatasetRole.DEVELOPMENT.value],
        "external_role_count": role_counts[DatasetRole.EXTERNAL.value],
        "clear_positive_count": label_counts[LabelStatus.CLEAR_POSITIVE.value],
        "clear_negative_count": label_counts[LabelStatus.CLEAR_NEGATIVE.value],
        "uncertain_count": label_counts[LabelStatus.UNCERTAIN.value],
        "conflict_count": conflict_count,
        "structure_eligible_count": structure_counts["eligible"],
        "structure_ineligible_count": structure_counts["ineligible"],
        "record_exclusion_count": len(exclusions),
        "compound_exclusion_count": len(compound_exclusions),
        "duplicate_group_counts": dict(sorted(duplicate_counts.items())),
        "development_exact_block_count": len(leakage.exact_block_keys),
        "development_connectivity_block_count": len(
            leakage.connectivity_block_keys
        ),
        "external_exact_overlap_count": leakage_counts[
            LeakageStatus.EXACT_OVERLAP.value
        ],
        "external_connectivity_overlap_count": leakage_counts[
            LeakageStatus.CONNECTIVITY_OVERLAP.value
        ],
        "external_tautomer_overlap_count": len(leakage.tautomer_overlap_ids),
        "primary_external_count": len(leakage.primary_external_ids),
        "tautomer_sensitivity_external_count": len(
            leakage.sensitivity_external_ids
        ),
        "split_eligible_role_count": eligibility_counts[
            SplitEligibility.ELIGIBLE.value
        ],
        "manual_review_completed": len(decisions),
        "manual_review_required": conflict_count,
        "manual_review_coverage": len(decisions) / conflict_count,
        "status": "validated_core",
    }


def validate_core(root: Path) -> CoreBuild:
    """执行全量纯内存重建；本函数不创建任何目录或文件。"""

    fingerprint, _ = input_fingerprint(root, parameters={"command": "validate-core"})
    records = load_records_all(root)
    validate_rows(records, SCHEMA_REGISTRY["modeling/records_all.csv"])
    exclusions = build_record_exclusions(records)
    compound_build: CompoundBuild = build_compounds(root, records)
    resolutions = build_core_role_resolutions(records, compound_build.rows)
    decisions = load_manual_reviews(root, resolutions)
    resolutions = apply_manual_reviews(resolutions, decisions)
    duplicate_groups = build_duplicate_groups(resolutions)
    _assert_frozen_views(root, compound_build.rows, resolutions)
    leakage = build_leakage(
        root, records, compound_build.rows, resolutions
    )
    finalized, compound_exclusions = finalize_role_resolutions(
        resolutions, leakage
    )
    candidates = build_review_candidates(resolutions, decisions)
    summary = _summary(
        records,
        exclusions,
        compound_build.rows,
        resolutions,
        duplicate_groups,
        finalized,
        compound_exclusions,
        leakage,
        decisions,
        fingerprint,
    )
    return CoreBuild(
        records_all=records,
        record_exclusions=exclusions,
        compounds=compound_build.rows,
        fingerprints=compound_build.fingerprints,
        role_resolutions=resolutions,
        finalized_role_resolutions=finalized,
        compound_exclusions=compound_exclusions,
        duplicate_groups=duplicate_groups,
        review_candidates=candidates,
        leakage=leakage,
        summary=summary,
    )
