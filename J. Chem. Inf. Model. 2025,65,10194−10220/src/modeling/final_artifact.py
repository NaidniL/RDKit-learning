"""冻结配置的最终模型 artifact 训练与可验证 manifest。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from modeling_dataset.serialization import canonical_json_bytes

from .experiment_manifest import sha256_file, write_json_artifact
from .featurizers import FeatureMatrix, feature_manifest
from .sanity_checks import class_counts


FINAL_ARTIFACT_FILES = frozenset(
    {
        "model.pkl",
        "preprocessing.pkl",
        "feature_manifest.json",
        "training_manifest.json",
        "training.log",
    }
)
FINAL_MANIFEST_VERSION = 1


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_canonical_final_config(path: Path) -> tuple[dict[str, Any], str]:
    """读取冻结 final 配置，并拒绝非 canonical JSON。"""

    raw = path.read_bytes()
    try:
        config = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("final model config 无法解析") from exc
    if not isinstance(config, dict) or raw != canonical_json_bytes(config):
        raise ValueError("final model config 必须是 canonical JSON object")
    return config, sha256_bytes(raw)


def validate_frozen_final_config(config: Mapping[str, Any]) -> None:
    """只接受已独立审核的 LightGBM descriptor 最终配置。"""

    required = {
        "descriptor_preprocessing",
        "deterministic",
        "external_access",
        "feature_set",
        "model_family",
        "n_jobs",
        "random_state",
        "selected_params",
        "selection_metric",
        "selection_policy_sha256",
        "selection_source",
        "status",
        "threshold",
        "training_strategy",
        "validation_auroc",
    }
    if set(config) != required:
        raise ValueError("final model config 字段集合不正确")
    if config["model_family"] != "LightGBM":
        raise ValueError("freeze-final 只允许 LightGBM")
    if config["feature_set"] != "rdkit_physicochemical_descriptors":
        raise ValueError("freeze-final 只允许 RDKit + physicochemical descriptors")
    if config["descriptor_preprocessing"] != {
        "constant_column_removal": True,
        "imputation": "median",
        "scaling": False,
    }:
        raise ValueError("freeze-final descriptor 预处理与冻结配置不一致")
    if config["external_access"] != "locked_until_independent_audit":
        raise PermissionError("final config 未保持 external 锁定")
    if config["training_strategy"] != {
        "development_candidate": "fit_train_evaluate_validation",
        "final_external_model": "fit_train_plus_validation_evaluate_external_once",
    }:
        raise ValueError("final config 未冻结 train+validation refit 策略")
    if config["threshold"] != 0.5:
        raise ValueError("freeze-final 的 threshold 必须为 0.5")
    if config["random_state"] != 42 or config["n_jobs"] != 1 or config["deterministic"] is not True:
        raise ValueError("freeze-final 只接受冻结的 deterministic 运行参数")
    expected_params = {
        "learning_rate": 0.03,
        "min_child_samples": 10,
        "n_estimators": 300,
        "num_leaves": 31,
        "reg_lambda": 0,
    }
    if config["selected_params"] != expected_params:
        raise ValueError("freeze-final 的 LightGBM params 与冻结配置不一致")


def _descriptor_preprocessing_summary(
    preprocessing: Any, matrix: FeatureMatrix
) -> dict[str, Any]:
    if matrix.binary_indices or not matrix.descriptor_indices:
        raise ValueError("final artifact 必须只包含 descriptors")
    descriptor_names = list(matrix.feature_names)
    descriptors = preprocessing.named_transformers_["descriptors"]
    imputer = descriptors.named_steps["impute"]
    selector = descriptors.named_steps["remove_constant"]
    support = np.asarray(selector.get_support(), dtype=bool)
    medians = np.asarray(imputer.statistics_, dtype=float)
    if len(medians) != len(descriptor_names) or len(support) != len(descriptor_names):
        raise ValueError("最终预处理器与 descriptor layout 不一致")
    return {
        "imputation": {
            "strategy": "median",
            "fitted_on": "train+validation",
            "medians": {name: float(value) for name, value in zip(descriptor_names, medians, strict=True)},
        },
        "constant_columns_removed": [
            name for name, retained in zip(descriptor_names, support, strict=True) if not retained
        ],
        "retained_descriptor_columns": [
            name for name, retained in zip(descriptor_names, support, strict=True) if retained
        ],
    }


def build_final_training_manifest(
    *,
    final_model_config_sha256: str,
    release_id: str,
    dataset_manifest_sha256: str,
    train_artifact: Mapping[str, Any],
    validation_artifact: Mapping[str, Any],
    labels: np.ndarray,
    matrix: FeatureMatrix,
    preprocessing: Any,
    lightgbm_params: Mapping[str, Any],
    runtime: Mapping[str, str],
    revision: str,
    model_path: Path,
    preprocessing_path: Path,
    feature_manifest_sha256: str,
) -> dict[str, Any]:
    """建立最终重训的无预测、无 external manifest。"""

    for name, value in {
        "final_model_config_sha256": final_model_config_sha256,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "feature_manifest_sha256": feature_manifest_sha256,
        "model_artifact_sha256": sha256_file(model_path),
        "preprocessing_artifact_sha256": sha256_file(preprocessing_path),
    }.items():
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(f"{name} 必须是小写 SHA-256")
    for path, metadata in {
        "train.csv": train_artifact,
        "validation.csv": validation_artifact,
    }.items():
        if set(metadata) != {"sha256", "bytes", "rows", "schema_version"}:
            raise ValueError(f"{path} artifact 元数据不完整")
    preprocessing_summary = _descriptor_preprocessing_summary(preprocessing, matrix)
    descriptors = list(matrix.feature_names)
    return {
        "training_manifest_version": FINAL_MANIFEST_VERSION,
        "final_model_config_sha256": final_model_config_sha256,
        "dataset_release_id": release_id,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "fit_split": "train_validation",
        "refit_data": {
            "sample_count": int(len(labels)),
            "class_counts": class_counts(labels),
            "class_count": int(len(set(int(value) for value in labels))),
        },
        "input_split_artifacts": {
            "train.csv": dict(train_artifact),
            "validation.csv": dict(validation_artifact),
        },
        "feature_set": "descriptors",
        "descriptor_list": descriptors,
        "feature_manifest_sha256": feature_manifest_sha256,
        "descriptor_preprocessing": preprocessing_summary,
        "lightgbm_params": dict(lightgbm_params),
        "random_state": int(lightgbm_params["random_state"]),
        "n_jobs": int(lightgbm_params["n_jobs"]),
        "deterministic": bool(lightgbm_params["deterministic"]),
        "threshold": 0.5,
        "code_revision": revision,
        "runtime_signature": dict(runtime),
        "model_artifact": {
            "path": "model.pkl",
            "sha256": sha256_file(model_path),
            "bytes": model_path.stat().st_size,
        },
        "preprocessing_artifact": {
            "path": "preprocessing.pkl",
            "sha256": sha256_file(preprocessing_path),
            "bytes": preprocessing_path.stat().st_size,
        },
        "external_access": "denied",
    }


def write_feature_manifest(path: Path, matrix: FeatureMatrix) -> str:
    return write_json_artifact(path, feature_manifest(matrix))


def write_final_training_manifest(path: Path, manifest: Mapping[str, Any]) -> str:
    if manifest.get("external_access") != "denied":
        raise PermissionError("final artifact manifest 必须记录 external_access=denied")
    return write_json_artifact(path, manifest)
