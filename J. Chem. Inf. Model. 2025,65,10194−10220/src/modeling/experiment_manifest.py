"""实验、特征和模型 artifact 的可验证清单。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from modeling_dataset.serialization import canonical_json_bytes, digest_file, write_bytes_fsync

from .evaluation_guard import assert_no_external_references


EXPERIMENT_MANIFEST_VERSION = 1


def sha256_file(path: Path) -> str:
    return digest_file(path).sha256


def write_json_artifact(path: Path, value: Mapping[str, Any]) -> str:
    """写 canonical JSON，并返回内容 SHA-256。"""

    payload = canonical_json_bytes(dict(value))
    write_bytes_fsync(path, payload)
    return hashlib.sha256(payload).hexdigest()


def validation_prediction_digest(
    compound_ids: list[str], labels: list[int], probabilities: list[float]
) -> tuple[str, int]:
    """记录 validation 预测序列的可复核 digest，不输出任何预测文件。"""

    if not (len(compound_ids) == len(labels) == len(probabilities)):
        raise ValueError("validation prediction digest 输入长度不一致")
    payload = canonical_json_bytes(
        [
            {
                "compound_id": compound_id,
                "normalized_label": label,
                "probability": probability,
            }
            for compound_id, label, probability in zip(
                compound_ids, labels, probabilities, strict=True
            )
        ]
    )
    return hashlib.sha256(payload).hexdigest(), len(compound_ids)


def build_experiment_manifest(
    *,
    release_id: str,
    release_manifest_sha256: str,
    config: Mapping[str, Any],
    feature_manifest_sha256: str,
    feature_manifest: Mapping[str, Any],
    model_artifact_sha256: str,
    model_artifact_bytes: int,
    train_cv_metrics: Mapping[str, float | None],
    validation_metrics: Mapping[str, float | None],
    best_params: Mapping[str, Any],
    split_artifacts: Mapping[str, Mapping[str, Any]],
    data_summary: Mapping[str, Any],
    runtime_signature: Mapping[str, str],
    code_revision: str,
    validation_confusion: Mapping[str, int],
    validation_prediction_sha256: str,
    validation_prediction_rows: int,
) -> dict[str, Any]:
    """构建开发期 manifest；刻意没有任何 external 指标或预测路径。"""

    assert_no_external_references(
        [
            json.dumps(config, sort_keys=True, ensure_ascii=False),
            json.dumps(feature_manifest, sort_keys=True, ensure_ascii=False),
            json.dumps(best_params, sort_keys=True, ensure_ascii=False),
        ]
    )
    for name, digest in {
        "release_manifest_sha256": release_manifest_sha256,
        "feature_manifest_sha256": feature_manifest_sha256,
        "model_artifact_sha256": model_artifact_sha256,
        "validation_prediction_sha256": validation_prediction_sha256,
    }.items():
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError(f"{name} 必须是小写 SHA-256")
    allowed_split_artifacts = {
        "splits/primary_reproduction/train.csv",
        "splits/primary_reproduction/validation.csv",
        "splits/primary_reproduction/train_tuning_cv_folds.csv",
    }
    required_split_artifacts = {
        "splits/primary_reproduction/train.csv",
        "splits/primary_reproduction/validation.csv",
    }
    if not required_split_artifacts <= set(split_artifacts) or not set(split_artifacts) <= allowed_split_artifacts:
        raise ValueError("实验 manifest 只能记录已读取的 train/validation/train_tuning_cv split hashes")
    for path, metadata in split_artifacts.items():
        if set(metadata) != {"sha256", "bytes", "rows", "schema_version"}:
            raise ValueError(f"split artifact 元数据不完整：{path}")
    experiment_id = hashlib.sha256(
        canonical_json_bytes(
            {
                "release_manifest_sha256": release_manifest_sha256,
                "configuration": dict(config),
                "feature_manifest_sha256": feature_manifest_sha256,
                "model_artifact_sha256": model_artifact_sha256,
            }
        )
    ).hexdigest()[:16]
    return {
        "experiment_manifest_version": EXPERIMENT_MANIFEST_VERSION,
        "experiment_id": f"EXP:{experiment_id}",
        "release_id": release_id,
        "release_manifest_sha256": release_manifest_sha256,
        "configuration": dict(config),
        "feature_manifest_sha256": feature_manifest_sha256,
        "feature_manifest": dict(feature_manifest),
        "split_artifacts": {path: dict(metadata) for path, metadata in split_artifacts.items()},
        "data_summary": dict(data_summary),
        "runtime_signature": dict(runtime_signature),
        "code_revision": code_revision,
        "model_artifact": {
            "path": "model.joblib",
            "sha256": model_artifact_sha256,
            "bytes": model_artifact_bytes,
        },
        "development_results": {
            "train_tuning_cv_metrics": dict(train_cv_metrics),
            "validation_metrics": dict(validation_metrics),
            "validation_confusion": dict(validation_confusion),
            "best_params_from_train_tuning_cv": dict(best_params),
        },
        "validation_prediction_digest": {
            "sha256": validation_prediction_sha256,
            "rows": validation_prediction_rows,
            "artifact_written": False,
        },
        "external_access": "denied",
    }


def write_experiment_manifest(path: Path, manifest: Mapping[str, Any]) -> str:
    if manifest.get("external_access") != "denied":
        raise PermissionError("模型批次 1 manifest 必须记录 external_access=denied")
    return write_json_artifact(path, manifest)


def load_experiment_manifest(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("experiment manifest 无法解析") from exc
    if not isinstance(value, dict) or value.get("experiment_manifest_version") != 1:
        raise ValueError("experiment manifest schema/version 非法")
    if raw != canonical_json_bytes(value):
        raise ValueError("experiment manifest 不是 canonical JSON")
    if value.get("external_access") != "denied":
        raise PermissionError("非最终评估 manifest 不得记录 external 访问")
    required = {
        "experiment_manifest_version",
        "experiment_id",
        "release_id",
        "release_manifest_sha256",
        "configuration",
        "feature_manifest_sha256",
        "feature_manifest",
        "split_artifacts",
        "data_summary",
        "runtime_signature",
        "code_revision",
        "model_artifact",
        "development_results",
        "validation_prediction_digest",
        "external_access",
    }
    if set(value) != required:
        raise ValueError("experiment manifest 字段集合不正确")
    return value
