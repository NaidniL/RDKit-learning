"""Manifest helpers and invariants for the frozen three-member v2 artifact."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from modeling_dataset.serialization import canonical_json_bytes

from .sanity_checks import class_counts


MEMBER_IDS = (
    "lightgbm_descriptors",
    "random_forest_maccs",
    "random_forest_ecfp4",
)
V2_FINAL_ARTIFACT_FILES = frozenset(
    {
        "artifact_hashes.json",
        "consensus_manifest.json",
        "environment_manifest.json",
        "feature_manifest.json",
        "member_lightgbm_descriptors_model.pkl",
        "member_lightgbm_descriptors_preprocessing.pkl",
        "member_random_forest_ecfp4_model.pkl",
        "member_random_forest_ecfp4_preprocessing.pkl",
        "member_random_forest_maccs_model.pkl",
        "member_random_forest_maccs_preprocessing.pkl",
        "training.log",
        "training_manifest.json",
        "v2_final_policy.json",
    }
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def member_artifact_paths(member_id: str) -> dict[str, str]:
    if member_id not in MEMBER_IDS:
        raise ValueError(f"未注册的 v2 member：{member_id}")
    return {
        "model": f"member_{member_id}_model.pkl",
        "preprocessing": f"member_{member_id}_preprocessing.pkl",
    }


def file_metadata(path: Path) -> dict[str, int | str]:
    return {"bytes": path.stat().st_size, "sha256": sha256_file(path)}


def build_training_manifest(
    *,
    policy_sha256: str,
    release_id: str,
    dataset_manifest_sha256: str,
    split_artifacts: Mapping[str, Mapping[str, Any]],
    labels: Any,
    members: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build an aggregate-only record of the one-time final refit."""

    if len(policy_sha256) != 64 or len(dataset_manifest_sha256) != 64:
        raise ValueError("v2 policy/release SHA-256 不正确")
    if [member.get("id") for member in members] != list(MEMBER_IDS):
        raise ValueError("v2 training manifest 成员顺序不正确")
    if set(split_artifacts) != {"train.csv", "validation.csv"}:
        raise ValueError("v2 final refit 只能记录 train/validation artifacts")
    return {
        "training_manifest_version": 1,
        "v2_final_policy_sha256": policy_sha256,
        "dataset_release_id": release_id,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "fit_split": "train_validation",
        "refit_data": {
            "sample_count": int(len(labels)),
            "class_counts": class_counts(labels),
            "class_count": int(len(set(int(value) for value in labels))),
        },
        "input_split_artifacts": {name: dict(value) for name, value in split_artifacts.items()},
        "members": [dict(member) for member in members],
        "external_access": "denied",
        "prediction_artifact_written": False,
    }


def build_consensus_manifest(
    *, policy: Mapping[str, Any], policy_sha256: str, members: list[Mapping[str, Any]]
) -> dict[str, Any]:
    """Record the mechanical v2 call rule without any sample predictions."""

    if [member.get("id") for member in members] != list(MEMBER_IDS):
        raise ValueError("consensus manifest 成员顺序不正确")
    return {
        "consensus_manifest_version": 1,
        "v2_final_policy_sha256": policy_sha256,
        "member_order": list(MEMBER_IDS),
        "member_artifacts": [
            {
                "id": member["id"],
                "model": dict(member["model_artifact"]),
                "preprocessing": dict(member["preprocessing_artifact"]),
            }
            for member in members
        ],
        "threshold": policy["consensus_rule"]["threshold"],
        "rule": {
            "positive": policy["consensus_rule"]["positive"],
            "negative": policy["consensus_rule"]["negative"],
            "otherwise": policy["consensus_rule"]["otherwise"],
        },
        "output_contract": dict(policy["output_contract"]),
        "applicability_domain": dict(policy["applicability_domain"]),
        "metrics": dict(policy["metrics"]),
        "external_driven_modification": "prohibited",
    }


def build_artifact_hashes(artifact_dir: Path) -> dict[str, Any]:
    """Hash every final artifact except this self-referential manifest itself."""

    names = {path.name for path in artifact_dir.iterdir()}
    required_without_self = set(V2_FINAL_ARTIFACT_FILES) - {"artifact_hashes.json"}
    if names != required_without_self:
        raise ValueError("生成 hashes 前 artifact 集合不完整")
    return {
        "artifact_hashes_version": 1,
        "excluded_self_referential_file": "artifact_hashes.json",
        "files": {
            name: file_metadata(artifact_dir / name) for name in sorted(required_without_self)
        },
    }


def validate_artifact_hashes(artifact_dir: Path, hashes: Mapping[str, Any]) -> None:
    """Verify the closed artifact set and all non-self hashes."""

    if {path.name for path in artifact_dir.iterdir()} != set(V2_FINAL_ARTIFACT_FILES):
        raise ValueError("v2 final artifact 文件集合不正确")
    expected = set(V2_FINAL_ARTIFACT_FILES) - {"artifact_hashes.json"}
    if hashes.get("artifact_hashes_version") != 1 or hashes.get(
        "excluded_self_referential_file"
    ) != "artifact_hashes.json":
        raise ValueError("artifact hashes schema 不正确")
    if set(hashes.get("files", {})) != expected:
        raise ValueError("artifact hashes 文件清单不完整")
    for name in expected:
        if hashes["files"][name] != file_metadata(artifact_dir / name):
            raise ValueError(f"artifact hash 不一致：{name}")


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()
