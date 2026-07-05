"""排除、角色解析和 duplicate group 测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.duplicate_groups import build_duplicate_groups  # noqa: E402
from modeling_dataset.enums import (  # noqa: E402
    DatasetRole,
    ExactDuplicateClass,
    LabelStatus,
)
from modeling_dataset.record_exclusions import build_record_exclusions  # noqa: E402
from modeling_dataset.role_resolution import (  # noqa: E402
    build_core_role_resolutions,
    duplicate_class,
)


def _record(
    key: str,
    label: int | None,
    *,
    candidate: str = "",
    model_ok: bool = True,
    reason: str = "",
    label_rule: str = "nonbinary_uncertain",
) -> dict[str, Any]:
    return {
        "record_key": key,
        "source_dataset": "cpdb",
        "source_record_id": key,
        "standard_inchikey": "AAAAAAAAAAAAAA-BBBBBBBBBB-C",
        "dataset_role": "development",
        "normalized_label": label,
        "label_candidate": candidate,
        "model_structure_ok": model_ok,
        "exclusion_reason": reason,
        "label_rule": label_rule,
    }


def test_record_exclusions_expand_every_reason() -> None:
    record = _record("r1", None, model_ok=False, reason="reason_a;reason_b")
    record["standard_inchikey"] = ""
    rows = build_record_exclusions([record])
    assert {row["exclusion_reason"] for row in rows} == {
        "no_standardized_key",
        "reason_a",
        "reason_b",
    }


def test_false_structure_without_reason_fails() -> None:
    with pytest.raises(ValueError, match="无明确原因"):
        build_record_exclusions([_record("r1", None, model_ok=False)])


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ((1, 0, 0), ExactDuplicateClass.SINGLE_RECORD),
        ((2, 0, 0), ExactDuplicateClass.MULTIPLE_CLEAR_SAME_LABEL),
        ((1, 0, 1), ExactDuplicateClass.MULTIPLE_CLEAR_WITH_NONBINARY),
        ((1, 1, 0), ExactDuplicateClass.MULTIPLE_CLEAR_CONFLICTING),
        ((0, 0, 2), ExactDuplicateClass.MULTIPLE_NONBINARY_ONLY),
    ],
)
def test_duplicate_group_five_classes(
    counts: tuple[int, int, int], expected: ExactDuplicateClass
) -> None:
    assert duplicate_class(
        positive=counts[0], negative=counts[1], nonbinary=counts[2]
    ) is expected


def test_role_resolution_partitions_records_and_counts_discordant() -> None:
    records = [
        _record("r1", 1),
        _record("r2", None, candidate="negative"),
        _record("r3", None, candidate="positive"),
    ]
    compounds = [
        {
            "compound_id": "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
            "structure_status": "eligible",
            "structure_reasons_json": [],
        }
    ]
    resolutions = build_core_role_resolutions(records, compounds)
    assert len(resolutions) == 1
    item = resolutions[0]
    assert item.dataset_role is DatasetRole.DEVELOPMENT
    assert item.label_status is LabelStatus.CLEAR_POSITIVE
    assert item.resolution_keys == ("r1",)
    assert item.nonresolution_keys == ("r2", "r3")
    assert item.discordant_nonclear_count == 1
    duplicate = build_duplicate_groups(resolutions)[0]
    assert duplicate["discordant_nonclear_count"] == 1
    assert duplicate["record_count"] == 3


def test_conflict_never_counts_discordant_nonclear() -> None:
    records = [
        _record("r1", 1),
        _record("r2", 0),
        _record("r3", None, candidate="negative"),
    ]
    compounds = [
        {
            "compound_id": "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
            "structure_status": "eligible",
            "structure_reasons_json": [],
        }
    ]
    item = build_core_role_resolutions(records, compounds)[0]
    assert item.label_status is LabelStatus.CONFLICT
    assert item.discordant_nonclear_count == 0


def test_endpoint_only_group_is_uncertain_nonresolution_role() -> None:
    records = [
        _record(
            "r1",
            None,
            label_rule="noncarcinogenicity_endpoint_only",
        )
    ]
    compounds = [
        {
            "compound_id": "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
            "structure_status": "eligible",
            "structure_reasons_json": [],
        }
    ]
    resolutions = build_core_role_resolutions(records, compounds)
    assert len(resolutions) == 1
    assert resolutions[0].label_status is LabelStatus.UNCERTAIN
    assert resolutions[0].resolution_keys == ()
    assert resolutions[0].nonresolution_keys == ("r1",)
    assert resolutions[0].endpoint_only
