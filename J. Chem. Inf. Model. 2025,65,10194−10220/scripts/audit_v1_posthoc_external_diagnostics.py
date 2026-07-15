#!/usr/bin/env python3
"""只读审核冻结 v1 的一次性 post-hoc external 诊断。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


AUTHORIZATION_PATH = ROOT / "configs" / "v1_posthoc_external_diagnostic_authorization_v1.json"
TRAINING_MANIFEST_PATH = ROOT / "models" / "final_model_v1" / "training_manifest.json"
EVALUATION_MANIFEST_PATH = (
    ROOT
    / "reports"
    / "modeling"
    / "final_external_evaluation_v1"
    / "external_evaluation_manifest.json"
)
DIAGNOSTIC_DIR = ROOT / "reports" / "modeling" / "v1_posthoc_external_diagnostics"
DIAGNOSTIC_MANIFEST_PATH = DIAGNOSTIC_DIR / "diagnostic_manifest.json"
REPORT_PATH = ROOT / "reports" / "modeling" / "v1_posthoc_external_diagnostics_audit.md"
EXPECTED_DIAGNOSTIC_FILES = {
    "diagnostic_manifest.json",
    "domain_aware_performance.md",
    "external_error_analysis.md",
    "similarity_scaffold_stratified_metrics.md",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 不是 canonical JSON object")
    return value


def check(results: list[tuple[str, bool]], label: str, condition: bool) -> None:
    results.append((label, bool(condition)))


def write_report(metadata: dict[str, Any], results: list[tuple[str, bool]]) -> int:
    passed = bool(results) and all(status for _, status in results)
    lines = [
        "# v1 post-hoc external diagnostics audit",
        "",
        f"状态：`{'PASS' if passed else 'FAIL'}`。",
        "",
        "## Immutable metadata",
        "",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in metadata.items())
    lines.extend(["", "## Checks", "", "| # | Check | Status |", "|---:|---|---|"])
    lines.extend(
        f"| {index} | {label} | {'PASS' if status else 'FAIL'} |"
        for index, (label, status) in enumerate(results, start=1)
    )
    lines.extend(
        [
            "",
            "本审核只读取授权文件、已有 manifests、诊断聚合报告和脚本；不读取任何 external split 行。",
            "该诊断曾在显式一次性授权下打开 primary external 以产生聚合描述，不能用于 v1 模型选择、调参或阈值修改。",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return 0 if passed else 1


def main() -> int:
    results: list[tuple[str, bool]] = []
    metadata: dict[str, Any] = {}
    try:
        authorization = load_canonical_json(AUTHORIZATION_PATH)
        training = load_canonical_json(TRAINING_MANIFEST_PATH)
        evaluation = load_canonical_json(EVALUATION_MANIFEST_PATH)
        diagnostic = load_canonical_json(DIAGNOSTIC_MANIFEST_PATH)
        release_pointer = load_canonical_json(
            ROOT / "releases" / "dataset_assembly" / "current_release.json"
        )
        release = load_canonical_json(
            ROOT / "releases" / "dataset_assembly" / release_pointer["manifest_path"]
        )
    except Exception as exc:
        check(results, f"输入与诊断 manifest 可读取：{type(exc).__name__}", False)
        return write_report(metadata, results)

    metadata = {
        "authorization_sha256": sha256(AUTHORIZATION_PATH),
        "final_training_manifest_sha256": sha256(TRAINING_MANIFEST_PATH),
        "final_evaluation_manifest_sha256": sha256(EVALUATION_MANIFEST_PATH),
        "dataset_release_id": training.get("dataset_release_id", "missing"),
        "external_prediction_digest": evaluation.get("external_prediction_digest", {}).get(
            "sha256", "missing"
        ),
    }
    check(
        results,
        "授权是 canonical JSON，且明确禁止模型变更与 prediction CSV",
        authorization.get("status") == "FROZEN_POST_HOC_EXTERNAL_DIAGNOSTIC_AUTHORIZED"
        and authorization.get("analysis_scope") == "post_hoc_descriptive_only"
        and authorization.get("model_change_prohibited") is True
        and authorization.get("prediction_csv_prohibited") is True
        and authorization.get("repeat_diagnostic_prohibited") is True,
    )
    check(
        results,
        "授权绑定到当前 final training 与 final external manifests",
        authorization.get("final_training_manifest_sha256") == sha256(TRAINING_MANIFEST_PATH)
        and authorization.get("final_evaluation_manifest_sha256") == sha256(EVALUATION_MANIFEST_PATH),
    )
    check(
        results,
        "诊断 manifest 绑定同一授权与冻结 manifests",
        diagnostic.get("authorization_sha256") == sha256(AUTHORIZATION_PATH)
        and diagnostic.get("final_training_manifest_sha256") == sha256(TRAINING_MANIFEST_PATH)
        and diagnostic.get("final_evaluation_manifest_sha256") == sha256(EVALUATION_MANIFEST_PATH),
    )
    check(
        results,
        "release id 与 dataset manifest 保持训练冻结版本",
        diagnostic.get("dataset_release_id") == training.get("dataset_release_id")
        == evaluation.get("dataset_release_id")
        and diagnostic.get("dataset_manifest_sha256")
        == training.get("dataset_manifest_sha256")
        == evaluation.get("dataset_manifest_sha256")
        == release_pointer.get("manifest_sha256"),
    )
    expected_external_split = {
        "path": "splits/external_test.csv",
        **release["release_artifacts"]["splits/external_test.csv"],
    }
    check(
        results,
        "external split metadata 与 release 及最终外测一致",
        diagnostic.get("external_split") == expected_external_split
        and evaluation.get("external_split") == expected_external_split,
    )
    check(
        results,
        "455 samples、固定 threshold 0.5，且聚合 confusion 精确复现",
        diagnostic.get("external_split", {}).get("rows") == 455
        and diagnostic.get("threshold") == training.get("threshold") == evaluation.get("threshold") == 0.5
        and diagnostic.get("reproduced_external_confusion") == evaluation.get("external_confusion"),
    )
    check(
        results,
        "prediction digest 被复现且未写样本级 artifact",
        diagnostic.get("prediction_digest")
        == evaluation.get("external_prediction_digest"),
    )
    check(
        results,
        "模型、预处理与 feature manifest 均与 final artifact 相同",
        diagnostic.get("model_artifact") == training.get("model_artifact")
        == evaluation.get("model_artifact")
        and diagnostic.get("preprocessing_artifact") == training.get("preprocessing_artifact")
        == evaluation.get("preprocessing_artifact")
        and diagnostic.get("feature_manifest_sha256")
        == training.get("feature_manifest_sha256")
        == evaluation.get("feature_manifest_sha256"),
    )
    check(
        results,
        "诊断目录仅含允许的聚合输出，且没有 CSV",
        {path.name for path in DIAGNOSTIC_DIR.iterdir()} == EXPECTED_DIAGNOSTIC_FILES
        and not list(DIAGNOSTIC_DIR.rglob("*.csv")),
    )
    source = (ROOT / "scripts" / "run_v1_posthoc_external_diagnostics.py").read_text(
        encoding="utf-8"
    )
    lock_index = source.find("if args.output_dir.exists()")
    external_access_index = source.find("assert_split_access(EXTERNAL_PATH")
    forbidden_feedback = (".fit(", "build_estimator(", "fit_with_train_tuning_cv(", "GridSearchCV")
    check(
        results,
        "一次性目录锁在 external access 前，且脚本无训练或调参调用",
        lock_index >= 0
        and external_access_index >= 0
        and lock_index < external_access_index
        and not any(item in source for item in forbidden_feedback),
    )
    check(
        results,
        "诊断输出显式维持 descriptive-only、model-change 与 CSV 禁止状态",
        diagnostic.get("external_access") == "post_hoc_diagnostic_once"
        and diagnostic.get("model_change_prohibited") is True
        and diagnostic.get("prediction_csv_prohibited") is True,
    )
    return write_report(metadata, results)


if __name__ == "__main__":
    raise SystemExit(main())
