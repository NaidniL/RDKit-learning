"""建模标签冲突人工审核输入测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.enums import (  # noqa: E402
    DatasetRole,
    ExactDuplicateClass,
    LabelStatus,
    ReviewStatus,
)
from modeling_dataset.manual_reviews import load_manual_reviews  # noqa: E402
from modeling_dataset.role_resolution import CoreRoleResolution  # noqa: E402
from modeling_dataset.schema_registry import SCHEMA_REGISTRY  # noqa: E402
from modeling_dataset.serialization import serialize_csv  # noqa: E402


def _resolution(status: LabelStatus = LabelStatus.CONFLICT) -> CoreRoleResolution:
    return CoreRoleResolution(
        compound_id="CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
        dataset_role=DatasetRole.DEVELOPMENT,
        role_normalized_label=None,
        label_status=status,
        review_status=(
            ReviewStatus.PENDING
            if status is LabelStatus.CONFLICT
            else ReviewStatus.NOT_REQUIRED
        ),
        resolution_keys=("r1", "r2"),
        nonresolution_keys=(),
        resolution_sources=("cpdb",),
        source_labels=("+", "-"),
        endpoint_only=False,
        clear_positive_count=1,
        clear_negative_count=1,
        nonbinary_count=0,
        discordant_nonclear_count=0,
        has_discordant_nonclear_evidence=False,
        exact_duplicate_class=ExactDuplicateClass.MULTIPLE_CLEAR_CONFLICTING,
        structure_status="eligible",
        structure_reasons=(),
    )


def _write_decisions(root: Path, rows: list[dict[str, object]]) -> None:
    path = root / "data" / "manual" / "modeling_conflict_decisions.csv"
    path.parent.mkdir(parents=True)
    path.write_bytes(
        serialize_csv(rows, SCHEMA_REGISTRY["modeling/conflict_reviews.csv"])
    )


def test_missing_manual_file_is_allowed(tmp_path: Path) -> None:
    assert load_manual_reviews(tmp_path, [_resolution()]) == {}


def test_valid_manual_decision_is_loaded(tmp_path: Path) -> None:
    row: dict[str, object] = {
        "compound_id": "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
        "dataset_role": "development",
        "decision": "confirm_exclude",
        "review_reason": "证据明确冲突",
        "reviewer": "reviewer",
        "reviewed_at_utc": "2026-07-05T12:00:00Z",
    }
    _write_decisions(tmp_path, [row])
    decisions = load_manual_reviews(tmp_path, [_resolution()])
    assert len(decisions) == 1


def test_unknown_or_nonconflict_manual_object_fails(tmp_path: Path) -> None:
    row: dict[str, object] = {
        "compound_id": "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
        "dataset_role": "development",
        "decision": "confirm_exclude",
        "review_reason": "reason",
        "reviewer": "reviewer",
        "reviewed_at_utc": "2026-07-05T12:00:00Z",
    }
    _write_decisions(tmp_path, [row])
    with pytest.raises(ValueError, match="非 conflict"):
        load_manual_reviews(tmp_path, [_resolution(LabelStatus.UNCERTAIN)])


def test_noncanonical_or_invalid_time_fails(tmp_path: Path) -> None:
    path = tmp_path / "data" / "manual" / "modeling_conflict_decisions.csv"
    path.parent.mkdir(parents=True)
    path.write_text(
        "compound_id,dataset_role,decision,review_reason,reviewer,reviewed_at_utc\n"
        "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C,development,confirm_exclude,reason,reviewer,2026-7-5\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="UTC"):
        load_manual_reviews(tmp_path, [_resolution()])
