"""建模标签冲突三步计数裁决测试。"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.enums import (  # noqa: E402
    DatasetRole,
    ExactDuplicateClass,
    LabelStatus,
    ReviewDecision,
    ReviewStatus,
)
from modeling_dataset.manual_reviews import (  # noqa: E402
    apply_conflict_resolution,
    build_review_candidates,
    conflict_decision,
)
from modeling_dataset.role_resolution import CoreRoleResolution  # noqa: E402


def _resolution(positive: int, negative: int) -> CoreRoleResolution:
    return CoreRoleResolution(
        compound_id="CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
        dataset_role=DatasetRole.DEVELOPMENT,
        role_normalized_label=None,
        label_status=LabelStatus.CONFLICT,
        review_status=ReviewStatus.PENDING,
        resolution_keys=tuple(f"r{index}" for index in range(positive + negative)),
        nonresolution_keys=(),
        resolution_sources=("cpdb",),
        source_labels=("+", "-"),
        endpoint_only=False,
        clear_positive_count=positive,
        clear_negative_count=negative,
        nonbinary_count=0,
        discordant_nonclear_count=0,
        has_discordant_nonclear_evidence=False,
        exact_duplicate_class=ExactDuplicateClass.MULTIPLE_CLEAR_CONFLICTING,
        structure_status="eligible",
        structure_reasons=(),
    )


def test_total_count_at_most_ten_is_excluded_first() -> None:
    decision, _, label = conflict_decision(_resolution(6, 4))
    assert decision is ReviewDecision.EXCLUDE_TOTAL_COUNT_LE_10
    assert label is None


def test_margin_at_most_ten_is_excluded_after_total_gate() -> None:
    decision, _, label = conflict_decision(_resolution(16, 6))
    assert decision is ReviewDecision.EXCLUDE_COUNT_MARGIN_LE_10
    assert label is None


def test_larger_positive_count_assigns_positive_label() -> None:
    resolved = apply_conflict_resolution([_resolution(17, 6)])[0]
    assert resolved.label_status is LabelStatus.CLEAR_POSITIVE
    assert resolved.role_normalized_label == 1
    assert resolved.review_status is ReviewStatus.AUTOMATIC_RESOLVED


def test_larger_negative_count_assigns_negative_label() -> None:
    resolved = apply_conflict_resolution([_resolution(6, 17)])[0]
    assert resolved.label_status is LabelStatus.CLEAR_NEGATIVE
    assert resolved.role_normalized_label == 0
    assert resolved.review_status is ReviewStatus.AUTOMATIC_RESOLVED


def test_excluded_conflict_is_retained_in_audit_candidates() -> None:
    resolved = apply_conflict_resolution([_resolution(6, 4)])[0]
    candidate = build_review_candidates([resolved])[0]
    assert candidate["decision"] == "exclude_total_count_le_10"
    assert candidate["resolved_label"] is None
    assert candidate["review_status"] == "automatic_exclude"
