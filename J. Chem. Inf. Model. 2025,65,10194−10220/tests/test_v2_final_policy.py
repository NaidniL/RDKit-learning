from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.v2_final_policy import (  # noqa: E402
    POLICY_STATUS,
    load_v2_final_policy,
    validate_v2_final_policy,
)


def test_v2_final_policy_is_canonical_and_has_the_frozen_conservative_rule() -> None:
    policy, policy_sha256 = load_v2_final_policy(ROOT / "configs" / "v2_final_policy_v1.json")
    assert len(policy_sha256) == 64
    assert policy["status"] == POLICY_STATUS
    assert policy["consensus_rule"] == {
        "member_order": ["lightgbm_descriptors", "random_forest_maccs", "random_forest_ecfp4"],
        "negative": "all probabilities < 0.5 -> noncarcinogen",
        "otherwise": "otherwise -> inconclusive",
        "positive": "all probabilities >= 0.5 -> carcinogen",
        "threshold": 0.5,
    }
    assert policy["applicability_domain"]["call_effect"] == "none"
    assert policy["external_evaluation"]["v1_primary_external"] == "prohibited"


def test_v2_final_policy_rejects_an_ad_rejection_rule_or_external_authorization() -> None:
    policy, _ = load_v2_final_policy(ROOT / "configs" / "v2_final_policy_v1.json")
    with_ad_rejection = copy.deepcopy(policy)
    with_ad_rejection["applicability_domain"]["call_effect"] = "inconclusive_below_threshold"
    with pytest.raises(ValueError, match="AD"):
        validate_v2_final_policy(with_ad_rejection)
    with_external_authorization = copy.deepcopy(policy)
    with_external_authorization["external_evaluation"]["status"] = "authorized"
    with pytest.raises(PermissionError, match="external"):
        validate_v2_final_policy(with_external_authorization)
