"""已审核 final artifact 的一次性 primary external 评估。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from modeling_dataset.serialization import canonical_json_bytes

from .experiment_manifest import sha256_file, write_json_artifact


EXTERNAL_FINAL_FILES = frozenset(
    {"external_evaluation_manifest.json", "external_evaluation.md"}
)
EXTERNAL_FINAL_MANIFEST_VERSION = 1
PRIMARY_EXTERNAL_PATH = "splits/external_test.csv"


def load_canonical_json_object(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path.name} 无法解析") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 必须是 canonical JSON object")
    return value


def sha256_json_rows(rows: list[dict[str, Any]]) -> str:
    """只记录 canonical prediction digest；绝不写 external 预测明细。"""

    return hashlib.sha256(canonical_json_bytes(rows)).hexdigest()


def verify_final_artifact_manifest(manifest_path: Path) -> dict[str, Any]:
    """验证 external-final 允许加载的唯一 final artifact 及其引用物。"""

    manifest = load_canonical_json_object(manifest_path)
    expected_files = {
        "model.pkl",
        "preprocessing.pkl",
        "feature_manifest.json",
        "training_manifest.json",
        "training.log",
    }
    if {item.name for item in manifest_path.parent.iterdir()} != expected_files:
        raise ValueError("final artifact 目录包含禁止或缺失文件")
    if manifest.get("training_manifest_version") != 1:
        raise ValueError("final training manifest version 非法")
    if manifest.get("external_access") != "denied":
        raise PermissionError("未冻结的 final artifact 不得进入 external-final")
    if manifest.get("fit_split") != "train_validation" or manifest.get("threshold") != 0.5:
        raise ValueError("final artifact 不是批准的 train+validation / threshold=0.5 模型")
    feature_manifest = load_canonical_json_object(manifest_path.parent / "feature_manifest.json")
    if sha256_file(manifest_path.parent / "feature_manifest.json") != manifest.get(
        "feature_manifest_sha256"
    ):
        raise ValueError("feature manifest SHA-256 不一致")
    if feature_manifest.get("feature_names") != manifest.get("descriptor_list"):
        raise ValueError("final artifact descriptor 列表不一致")
    for name, path_key in (("model", "model.pkl"), ("preprocessing", "preprocessing.pkl")):
        artifact = manifest.get(f"{name}_artifact")
        if not isinstance(artifact, dict) or artifact.get("path") != path_key:
            raise ValueError(f"{name} artifact 元数据不正确")
        path = manifest_path.parent / path_key
        if sha256_file(path) != artifact.get("sha256") or path.stat().st_size != artifact.get("bytes"):
            raise ValueError(f"{name} artifact SHA-256 或 bytes 不一致")
    return manifest


def build_external_evaluation_manifest(
    *,
    training_manifest_path: Path,
    training_manifest: Mapping[str, Any],
    external_artifact: Mapping[str, Any],
    metrics: Mapping[str, float | None],
    confusion: Mapping[str, int],
    prediction_digest: str,
    prediction_rows: int,
    performed_at_utc: str,
    code_revision: str,
    runtime_signature: Mapping[str, str],
) -> dict[str, Any]:
    if set(external_artifact) != {"sha256", "bytes", "rows", "schema_version"}:
        raise ValueError("external split artifact 元数据不完整")
    training_sha = sha256_file(training_manifest_path)
    evaluation_id = hashlib.sha256(
        canonical_json_bytes(
            {
                "training_manifest_sha256": training_sha,
                "dataset_manifest_sha256": training_manifest["dataset_manifest_sha256"],
                "external_split_sha256": external_artifact["sha256"],
            }
        )
    ).hexdigest()[:16]
    return {
        "external_evaluation_manifest_version": EXTERNAL_FINAL_MANIFEST_VERSION,
        "external_evaluation_id": f"EXT:{evaluation_id}",
        "performed_at_utc": performed_at_utc,
        "approval": {
            "final_artifact_independent_audit": "PASS",
            "model_training_manifest_sha256": training_sha,
        },
        "dataset_release_id": training_manifest["dataset_release_id"],
        "dataset_manifest_sha256": training_manifest["dataset_manifest_sha256"],
        "external_split": {
            "path": PRIMARY_EXTERNAL_PATH,
            **dict(external_artifact),
        },
        "model_artifact": dict(training_manifest["model_artifact"]),
        "preprocessing_artifact": dict(training_manifest["preprocessing_artifact"]),
        "feature_manifest_sha256": training_manifest["feature_manifest_sha256"],
        "threshold": 0.5,
        "external_metrics": dict(metrics),
        "external_confusion": dict(confusion),
        "external_prediction_digest": {
            "sha256": prediction_digest,
            "rows": prediction_rows,
            "artifact_written": False,
        },
        "code_revision": code_revision,
        "runtime_signature": dict(runtime_signature),
        "external_access": "granted_final_once",
    }


def write_external_evaluation_manifest(path: Path, manifest: Mapping[str, Any]) -> str:
    if manifest.get("external_access") != "granted_final_once":
        raise PermissionError("external-final manifest 必须记录一次性授权")
    return write_json_artifact(path, manifest)
