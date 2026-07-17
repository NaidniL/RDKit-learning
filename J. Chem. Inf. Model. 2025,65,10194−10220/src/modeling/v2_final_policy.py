"""Loading and structural validation for the frozen v2 final policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from modeling_dataset.serialization import canonical_json_bytes


POLICY_STATUS = "FROZEN_FINAL_POLICY_PRE_EXTERNAL"
MEMBER_ORDER = (
    "lightgbm_descriptors",
    "random_forest_maccs",
    "random_forest_ecfp4",
)
CONSENSUS_RULE = {
    "negative": "all probabilities < 0.5 -> noncarcinogen",
    "otherwise": "otherwise -> inconclusive",
    "positive": "all probabilities >= 0.5 -> carcinogen",
    "threshold": 0.5,
}


def sha256_file(path: Path) -> str:
    """Return the lower-case SHA-256 digest of a local artifact."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_v2_final_policy(path: Path) -> tuple[dict[str, Any], str]:
    """Load a canonical, structurally valid v2 final-policy artifact."""

    raw = path.read_bytes()
    try:
        policy = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("v2 final policy 无法解析") from exc
    if not isinstance(policy, dict) or raw != canonical_json_bytes(policy):
        raise ValueError("v2 final policy 必须是 canonical JSON object")
    validate_v2_final_policy(policy)
    return policy, hashlib.sha256(raw).hexdigest()


def _require_keys(value: Mapping[str, Any], expected: set[str], *, context: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{context} 字段集合不正确")


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= set("0123456789abcdef")


def validate_v2_final_policy(policy: Mapping[str, Any]) -> None:
    """Reject policy changes that would silently alter the preregistration."""

    _require_keys(
        policy,
        {
            "applicability_domain",
            "consensus_rule",
            "data_identity",
            "external_evaluation",
            "feature_registry",
            "members",
            "metrics",
            "output_contract",
            "policy_prohibitions",
            "prerequisites",
            "status",
            "training",
            "v1_baseline",
            "version",
        },
        context="v2 final policy",
    )
    if policy["version"] != 1 or policy["status"] != POLICY_STATUS:
        raise ValueError("v2 final policy version 或 status 不正确")

    rule = policy["consensus_rule"]
    if not isinstance(rule, Mapping) or rule.get("member_order") != list(MEMBER_ORDER):
        raise ValueError("v2 成员顺序未冻结")
    if {key: rule.get(key) for key in CONSENSUS_RULE} != CONSENSUS_RULE:
        raise ValueError("v2 unanimity 规则或阈值未冻结")

    data = policy["data_identity"]
    if not isinstance(data, Mapping):
        raise ValueError("v2 data identity 必须为 object")
    _require_keys(
        data,
        {"dataset_manifest_sha256", "final_refit", "formal_release_id", "split_artifacts"},
        context="data_identity",
    )
    if not _is_sha256(data["dataset_manifest_sha256"]):
        raise ValueError("dataset manifest SHA-256 不正确")
    if data["final_refit"] != {
        "sample_count": 921,
        "source_splits": [
            "splits/primary_reproduction/train.csv",
            "splits/primary_reproduction/validation.csv",
        ],
    }:
        raise ValueError("v2 final refit population 未冻结为 train+validation 921")

    members = policy["members"]
    if not isinstance(members, list) or [item.get("id") for item in members] != list(MEMBER_ORDER):
        raise ValueError("v2 final members 未冻结")
    if any(item.get("probability_output") != "predict_proba positive class" for item in members):
        raise ValueError("v2 成员 probability output 未冻结")
    if [item.get("model") for item in members] != ["lightgbm", "random_forest", "random_forest"]:
        raise ValueError("v2 成员 model family 未冻结")

    output_contract = policy["output_contract"]
    if output_contract.get("contract_id") != "v2_output_contract_v1" or not _is_sha256(
        output_contract.get("sha256")
    ):
        raise ValueError("v2 output contract 未绑定")

    ad = policy["applicability_domain"]
    if ad.get("call_effect") != "none" or ad.get("reporting_only") is not True:
        raise ValueError("保守 AD 政策不得改变 v2 prediction")
    if ad.get("reference_population") != "final_refit_train_validation":
        raise ValueError("AD reference population 未冻结")

    external = policy["external_evaluation"]
    if external != {
        "new_external_manifest": "must_be_bound_and_hashed_before_any_read",
        "policy_change_after_new_external_read": "prohibited",
        "status": "not_authorized_by_this_policy",
        "v1_primary_external": "prohibited",
    }:
        raise PermissionError("external policy 不满足 v2 预注册隔离要求")

    metrics = policy["metrics"]
    if metrics.get("primary") != [
        "coverage",
        "covered_set_mcc",
        "covered_set_sensitivity",
        "covered_set_specificity",
    ]:
        raise ValueError("v2 一级指标未冻结")
    if metrics.get("success_criteria") != {
        "covered_set_mcc_vs_v1_same_covered_subset": "greater_or_equal",
        "covered_set_sensitivity_minimum": 0.65,
        "covered_set_specificity_minimum": 0.65,
        "coverage_minimum": 0.65,
        "inconclusive_mean_member_error_rate_vs_covered": "greater",
    }:
        raise ValueError("v2 成功标准未冻结")
    if set(policy["policy_prohibitions"]) != {
        "additional_member_models",
        "applicability_domain_rejection_threshold",
        "calibration",
        "dynamic_probability_threshold",
        "external_driven_modification",
        "majority_vote",
        "weighted_ensemble",
    }:
        raise ValueError("v2 禁止的规则扩展未冻结")
    if any(not _is_sha256(value) for value in policy["prerequisites"].values()):
        raise ValueError("v2 development prerequisite hashes 不正确")
