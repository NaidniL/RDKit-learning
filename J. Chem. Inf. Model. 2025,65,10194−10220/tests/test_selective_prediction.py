from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.selective_prediction import (  # noqa: E402
    V2_OUTPUT_FIELDS,
    confidence_scores,
    error_pattern_counts,
    top_coverage_mask,
    unanimity_mask,
    v2_output_records,
)
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


def test_unanimity_and_error_patterns_are_aggregate_and_aligned() -> None:
    probabilities = np.asarray(
        [[0.1, 0.2, 0.3], [0.9, 0.8, 0.7], [0.9, 0.4, 0.8], [0.2, 0.7, 0.8]]
    )
    assert unanimity_mask(probabilities, threshold=0.5).tolist() == [True, True, False, False]
    assert error_pattern_counts([0, 1, 1, 0], probabilities, threshold=0.5) == {
        "any_member_wrong": 2,
        "at_least_two_members_wrong": 1,
        "all_members_wrong": 0,
    }


def test_v2_output_contract_has_only_three_calls_and_marks_disagreement_for_review() -> None:
    outputs = v2_output_records(
        [[0.5, 0.7, 0.9], [0.1, 0.2, 0.49], [0.8, 0.2, 0.9]], threshold=0.5
    )
    assert [tuple(record) for record in outputs] == [V2_OUTPUT_FIELDS] * 3
    assert outputs == [
        {
            "schema_version": "v2_output_contract_v1",
            "prediction": "carcinogen",
            "decision_reason": "unanimous_carcinogen",
            "review_required": False,
        },
        {
            "schema_version": "v2_output_contract_v1",
            "prediction": "noncarcinogen",
            "decision_reason": "unanimous_noncarcinogen",
            "review_required": False,
        },
        {
            "schema_version": "v2_output_contract_v1",
            "prediction": "inconclusive",
            "decision_reason": "member_disagreement",
            "review_required": True,
        },
    ]


def test_frozen_output_contract_matches_the_runtime_output() -> None:
    contract_path = ROOT / "configs" / "v2_output_contract_v1.json"
    raw = contract_path.read_bytes()
    contract = json.loads(raw.decode("utf-8"))
    assert raw == canonical_json_bytes(contract)
    assert contract["status"] == "FROZEN_OUTPUT_CONTRACT_NOT_FINAL_MODEL_POLICY"
    assert tuple(contract["output"]["field_order"]) == V2_OUTPUT_FIELDS
    assert contract["decision_rule"] == {
        "members": ["lightgbm_descriptors", "random_forest_maccs", "random_forest_ecfp4"],
        "negative": "all member probabilities < 0.5",
        "otherwise": "inconclusive",
        "positive": "all member probabilities >= 0.5",
        "threshold": 0.5,
    }
    assert contract["output"]["values"] == {
        "carcinogen": {"decision_reason": "unanimous_carcinogen", "review_required": False},
        "inconclusive": {"decision_reason": "member_disagreement", "review_required": True},
        "noncarcinogen": {"decision_reason": "unanimous_noncarcinogen", "review_required": False},
    }
    outputs = v2_output_records([[0.9, 0.9, 0.9], [0.1, 0.9, 0.1]], threshold=0.5)
    for output in outputs:
        assert output["schema_version"] == contract["output"]["schema_version"]
        expected = contract["output"]["values"][output["prediction"]]
        assert output["decision_reason"] == expected["decision_reason"]
        assert output["review_required"] is expected["review_required"]


def test_risk_coverage_selection_is_deterministic_and_uses_secondary_score() -> None:
    primary = [0.5, 0.5, 0.4, 0.1]
    selected = top_coverage_mask(primary, coverage=0.5, secondary_score=[0.1, 0.9, 0.0, 0.0])
    assert selected.tolist() == [True, True, False, False]
    assert top_coverage_mask(primary, coverage=0.25, secondary_score=[0.1, 0.9, 0.0, 0.0]).tolist() == [
        False,
        True,
        False,
        False,
    ]


def test_confidence_scores_and_invalid_coverage_are_checked() -> None:
    scores = confidence_scores([[0.9, 0.8, 0.7], [0.4, 0.6, 0.5]], threshold=0.5)
    assert scores["hard_vote_agreement"].tolist() == [1.0, 2 / 3]
    with pytest.raises(ValueError, match="coverage"):
        top_coverage_mask([0.1, 0.2], coverage=0)
