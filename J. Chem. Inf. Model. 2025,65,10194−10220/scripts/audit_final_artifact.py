#!/usr/bin/env python3
"""独立审核 final artifact；不读取任何 split 行，更不会读取 external。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402

from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


FINAL_FILES = {
    "model.pkl",
    "preprocessing.pkl",
    "feature_manifest.json",
    "training_manifest.json",
    "training.log",
}
EXPECTED_CONFIG_SHA256 = "19a0ca3d720c940e6574b43abfee13a6f7ca76f73d67b13ef60b7844fef6f486"
EXPECTED_PARAMS = {
    "learning_rate": 0.03,
    "min_child_samples": 10,
    "n_estimators": 300,
    "num_leaves": 31,
    "reg_lambda": 0,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 不是 canonical JSON object")
    return value


def record(results: list[tuple[str, bool]], message: str, condition: bool) -> None:
    results.append((message, bool(condition)))


def main() -> int:
    artifact_dir = ROOT / "models" / "final_model_v1"
    report_path = ROOT / "reports" / "modeling" / "final_artifact_independent_audit.md"
    results: list[tuple[str, bool]] = []
    metadata: dict[str, Any] = {"artifact_dir": str(artifact_dir)}

    record(results, "1. final artifact 目录存在", artifact_dir.is_dir())
    observed_files = {item.name for item in artifact_dir.iterdir()} if artifact_dir.is_dir() else set()
    record(results, "2. 仅存在批准的五个 artifact", observed_files == FINAL_FILES)
    if observed_files != FINAL_FILES:
        return write_report(report_path, metadata, results)

    try:
        config_path = ROOT / "configs" / "final_model_config_v1.json"
        config = load_canonical_json(config_path)
        manifest = load_canonical_json(artifact_dir / "training_manifest.json")
        feature_manifest = load_canonical_json(artifact_dir / "feature_manifest.json")
        model = joblib.load(artifact_dir / "model.pkl")
        preprocessing = joblib.load(artifact_dir / "preprocessing.pkl")
    except Exception as exc:
        record(results, f"3. JSON 与 pickle artifact 可读取：{type(exc).__name__}", False)
        return write_report(report_path, metadata, results)

    metadata.update(
        {
            "final_model_config_sha256": manifest.get("final_model_config_sha256", "missing"),
            "dataset_release_id": manifest.get("dataset_release_id", "missing"),
            "dataset_manifest_sha256": manifest.get("dataset_manifest_sha256", "missing"),
            "model_artifact_sha256": manifest.get("model_artifact", {}).get("sha256", "missing"),
            "preprocessing_artifact_sha256": manifest.get("preprocessing_artifact", {}).get("sha256", "missing"),
        }
    )
    required_keys = {
        "training_manifest_version",
        "final_model_config_sha256",
        "dataset_release_id",
        "dataset_manifest_sha256",
        "fit_split",
        "refit_data",
        "input_split_artifacts",
        "feature_set",
        "descriptor_list",
        "feature_manifest_sha256",
        "descriptor_preprocessing",
        "lightgbm_params",
        "random_state",
        "n_jobs",
        "deterministic",
        "threshold",
        "code_revision",
        "runtime_signature",
        "model_artifact",
        "preprocessing_artifact",
        "external_access",
    }
    record(results, "3. training manifest schema/version 固定", set(manifest) == required_keys and manifest.get("training_manifest_version") == 1)
    record(results, "4. final config SHA-256 与冻结配置相符", sha256(config_path) == EXPECTED_CONFIG_SHA256 == manifest.get("final_model_config_sha256"))
    record(results, "5. frozen config 仍为 LightGBM + descriptors", config.get("model_family") == "LightGBM" and config.get("feature_set") == "rdkit_physicochemical_descriptors")
    record(results, "6. fit split 是 train+validation", manifest.get("fit_split") == "train_validation")
    refit = manifest.get("refit_data", {})
    record(results, "7. refit 样本数和类别计数完整", refit == {"sample_count": 921, "class_counts": {"0": 503, "1": 418}, "class_count": 2})

    try:
        pointer = load_canonical_json(ROOT / "releases" / "dataset_assembly" / "current_release.json")
        release_manifest_path = ROOT / "releases" / "dataset_assembly" / pointer["manifest_path"]
        release_manifest = load_canonical_json(release_manifest_path)
        expected_splits = {
            "train.csv": release_manifest["release_artifacts"]["splits/primary_reproduction/train.csv"],
            "validation.csv": release_manifest["release_artifacts"]["splits/primary_reproduction/validation.csv"],
        }
        release_matches = (
            pointer.get("release_id") == manifest.get("dataset_release_id")
            and pointer.get("manifest_sha256") == manifest.get("dataset_manifest_sha256")
            and manifest.get("input_split_artifacts") == expected_splits
        )
    except Exception:
        release_matches = False
    record(results, "8. release ID、manifest 及 train/validation hashes 相符", release_matches)

    descriptors = manifest.get("descriptor_list", [])
    record(results, "9. feature set 是 220 个 descriptors", manifest.get("feature_set") == "descriptors" and len(descriptors) == 220 and feature_manifest.get("feature_names") == descriptors)
    record(results, "10. feature manifest SHA-256 相符", sha256(artifact_dir / "feature_manifest.json") == manifest.get("feature_manifest_sha256"))
    try:
        descriptor_pipeline = preprocessing.named_transformers_["descriptors"]
        imputer = descriptor_pipeline.named_steps["impute"]
        selector = descriptor_pipeline.named_steps["remove_constant"]
        support = np.asarray(selector.get_support(), dtype=bool)
        summary = manifest["descriptor_preprocessing"]
        expected_removed = [name for name, retained in zip(descriptors, support, strict=True) if not retained]
        expected_retained = [name for name, retained in zip(descriptors, support, strict=True) if retained]
        expected_medians = {name: float(value) for name, value in zip(descriptors, imputer.statistics_, strict=True)}
        preprocessing_matches = (
            summary["imputation"] == {"strategy": "median", "fitted_on": "train+validation", "medians": expected_medians}
            and summary["constant_columns_removed"] == expected_removed
            and summary["retained_descriptor_columns"] == expected_retained
        )
    except Exception:
        preprocessing_matches = False
    record(results, "11. median 在 train+validation 拟合且常数列移除可复核", preprocessing_matches)
    actual_params = model.get_params(deep=False) if hasattr(model, "get_params") else {}
    expected_runtime_params = {**EXPECTED_PARAMS, "random_state": 42, "n_jobs": 1, "deterministic": True}
    record(results, "12. LightGBM params、random_state、n_jobs、deterministic 一致", all(actual_params.get(key) == value for key, value in expected_runtime_params.items()) and all(manifest.get(key) == value for key, value in {"random_state": 42, "n_jobs": 1, "deterministic": True}.items()) and all(manifest.get("lightgbm_params", {}).get(key) == value for key, value in expected_runtime_params.items()))
    record(results, "13. threshold 固定为 0.5", manifest.get("threshold") == 0.5 == config.get("threshold"))
    record(results, "14. model artifact SHA-256 和 bytes 相符", sha256(artifact_dir / "model.pkl") == manifest.get("model_artifact", {}).get("sha256") and (artifact_dir / "model.pkl").stat().st_size == manifest.get("model_artifact", {}).get("bytes"))
    record(results, "15. preprocessing artifact SHA-256 和 bytes 相符", sha256(artifact_dir / "preprocessing.pkl") == manifest.get("preprocessing_artifact", {}).get("sha256") and (artifact_dir / "preprocessing.pkl").stat().st_size == manifest.get("preprocessing_artifact", {}).get("bytes"))
    record(results, "16. code revision 与 runtime signature 已记录", bool(manifest.get("code_revision")) and {"python", "platform", "numpy", "scikit_learn", "rdkit", "lightgbm"} <= set(manifest.get("runtime_signature", {})))
    record(results, "17. external access 明确 denied", manifest.get("external_access") == "denied")
    record(results, "18. 不含预测、指标或未批准 artifact", not ({"metrics", "predictions", "external_results", "validation_results"} & set(manifest)) and "external_access=denied" in (artifact_dir / "training.log").read_text(encoding="utf-8"))
    return write_report(report_path, metadata, results)


def write_report(path: Path, metadata: dict[str, Any], results: list[tuple[str, bool]]) -> int:
    passed = bool(results) and all(status for _, status in results)
    lines = ["# Final artifact independent audit", "", f"状态：`{'PASS' if passed else 'FAIL'}`。", "", "## Immutable metadata", ""]
    lines.extend(f"- {key}: `{value}`" for key, value in metadata.items())
    lines.extend(["", "## Checks", "", "| # | Check | Status |", "|---:|---|---|"])
    lines.extend(f"| {index} | {message} | {'PASS' if status else 'FAIL'} |" for index, (message, status) in enumerate(results, start=1))
    lines.extend(["", "本审核只读取 final artifacts、冻结 config、release pointer/manifest 元数据；不读取任何 split 行或 external 数据。", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
