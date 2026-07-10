"""最终角色状态优先级与排除原因完整性测试。"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.enums import (  # noqa: E402
    DatasetRole,
    ExactDuplicateClass,
    LabelStatus,
    LeakageStatus,
    ReviewStatus,
)
from modeling_dataset.leakage import LeakageBuild  # noqa: E402
from modeling_dataset.role_finalization import (  # noqa: E402
    finalize_role_resolutions,
)
from modeling_dataset.role_resolution import CoreRoleResolution  # noqa: E402


def _base(compound_id: str, role: DatasetRole) -> CoreRoleResolution:
    return CoreRoleResolution(
        compound_id=compound_id,
        dataset_role=role,
        role_normalized_label=1,
        label_status=LabelStatus.CLEAR_POSITIVE,
        review_status=ReviewStatus.NOT_REQUIRED,
        resolution_keys=(f"REC:{compound_id}",),
        nonresolution_keys=(),
        resolution_sources=("cpdb" if role is DatasetRole.DEVELOPMENT else "ccris",),
        source_labels=("positive",),
        endpoint_only=False,
        clear_positive_count=1,
        clear_negative_count=0,
        nonbinary_count=0,
        discordant_nonclear_count=0,
        has_discordant_nonclear_evidence=False,
        exact_duplicate_class=ExactDuplicateClass.SINGLE_RECORD,
        structure_status="eligible",
        structure_reasons=(),
    )


def test_final_state_precedence_and_concurrent_reasons() -> None:
    dev = replace(
        _base("CMP:DEV", DatasetRole.DEVELOPMENT),
        role_normalized_label=None,
        label_status=LabelStatus.CONFLICT,
        review_status=ReviewStatus.PENDING,
        structure_status="ineligible",
        structure_reasons=("structure_representation_conflict",),
        clear_negative_count=1,
        exact_duplicate_class=ExactDuplicateClass.MULTIPLE_CLEAR_CONFLICTING,
    )
    external_uncertain = replace(
        _base("CMP:UNCERTAIN", DatasetRole.EXTERNAL),
        role_normalized_label=None,
        label_status=LabelStatus.UNCERTAIN,
        resolution_keys=(),
        nonresolution_keys=("REC:uncertain",),
        clear_positive_count=0,
        nonbinary_count=1,
    )
    external_clear = _base("CMP:CLEAR", DatasetRole.EXTERNAL)
    statuses = {
        ("CMP:DEV", "development"): LeakageStatus.NOT_APPLICABLE,
        ("CMP:UNCERTAIN", "external"): LeakageStatus.EXACT_OVERLAP,
        ("CMP:CLEAR", "external"): LeakageStatus.CONNECTIVITY_OVERLAP,
    }
    leakage = LeakageBuild(
        exact_block_keys=frozenset(),
        connectivity_block_keys=frozenset(),
        exact_block_rows=[],
        connectivity_block_rows=[],
        role_statuses=statuses,
        tautomer_overlap_ids=frozenset({"CMP:CLEAR"}),
        tautomer_overlap_rows=[],
        primary_external_ids=frozenset(),
        sensitivity_external_ids=frozenset(),
    )
    rows, exclusions = finalize_role_resolutions(
        [dev, external_uncertain, external_clear], leakage
    )
    by_id = {row["compound_id"]: row for row in rows}

    assert by_id["CMP:DEV"]["split_eligibility"] == "ineligible_structure"
    assert by_id["CMP:DEV"]["exclusion_reasons_json"] == [
        "label_conflict",
        "label_conflict_total_count_le_10",
        "structure_representation_conflict",
    ]
    assert "confirmed_exact_label_conflict_exclude" not in by_id["CMP:DEV"][
        "resolution_rules_json"
    ]
    assert by_id["CMP:UNCERTAIN"]["split_eligibility"] == "ineligible_label"
    assert by_id["CMP:UNCERTAIN"]["exclusion_reasons_json"] == [
        "external_exact_overlap",
        "label_uncertain",
    ]
    assert by_id["CMP:CLEAR"]["split_eligibility"] == "ineligible_leakage"
    assert by_id["CMP:CLEAR"]["has_tautomer_overlap"] is True
    assert {
        (row["compound_id"], row["exclusion_reason"]) for row in exclusions
    } == {
        ("CMP:DEV", "label_conflict"),
        ("CMP:DEV", "label_conflict_total_count_le_10"),
        ("CMP:DEV", "structure_representation_conflict"),
        ("CMP:UNCERTAIN", "external_exact_overlap"),
        ("CMP:UNCERTAIN", "label_uncertain"),
        ("CMP:CLEAR", "external_connectivity_overlap"),
    }
