#!/usr/bin/env python3
"""只读审核一次性 primary external 结果；唯一写入为 Markdown 报告。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


FINAL_ARTIFACT_DIR = ROOT / "models" / "final_model_v1"
EVALUATION_DIR = ROOT / "reports" / "modeling" / "final_external_evaluation_v1"
REPORT_PATH = ROOT / "reports" / "modeling" / "final_external_evaluation_audit.md"
EXPECTED_EVALUATION_FILES = {
    "external_evaluation_manifest.json",
    "external_evaluation.md",
}
ALLOWED_CHANGED_PATHS = {
    "models/final_model_v1/feature_manifest.json",
    "models/final_model_v1/model.pkl",
    "models/final_model_v1/preprocessing.pkl",
    "models/final_model_v1/training.log",
    "models/final_model_v1/training_manifest.json",
    "scripts/train_model.py",
    "scripts/audit_final_artifact.py",
    "scripts/audit_final_external_evaluation.py",
    "src/modeling/dataset_release_reader.py",
    "src/modeling/external_final.py",
    "src/modeling/final_artifact.py",
    "src/modeling/metrics.py",
    "reports/modeling/final_artifact_independent_audit.md",
    "reports/modeling/final_external_evaluation_audit.md",
    "reports/modeling/final_external_evaluation_v1/external_evaluation.md",
    "reports/modeling/final_external_evaluation_v1/external_evaluation_manifest.json",
    "reports/modeling/final_model_v1_summary.md",
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


def main() -> int:
    results: list[tuple[str, bool]] = []
    metadata: dict[str, Any] = {}
    try:
        evaluation = load_canonical_json(EVALUATION_DIR / "external_evaluation_manifest.json")
        training = load_canonical_json(FINAL_ARTIFACT_DIR / "training_manifest.json")
        release_pointer = load_canonical_json(
            ROOT / "releases" / "dataset_assembly" / "current_release.json"
        )
        release = load_canonical_json(
            ROOT / "releases" / "dataset_assembly" / release_pointer["manifest_path"]
        )
    except Exception as exc:
        check(results, f"输入 manifest 可读取：{type(exc).__name__}", False)
        return write_report(metadata, results)

    metadata = {
        "external_evaluation_id": evaluation.get("external_evaluation_id", "missing"),
        "model_training_manifest_sha256": evaluation.get("approval", {}).get(
            "model_training_manifest_sha256", "missing"
        ),
        "dataset_release_id": evaluation.get("dataset_release_id", "missing"),
        "dataset_manifest_sha256": evaluation.get("dataset_manifest_sha256", "missing"),
        "external_split_sha256": evaluation.get("external_split", {}).get("sha256", "missing"),
        "external_prediction_digest": evaluation.get("external_prediction_digest", {}).get(
            "sha256", "missing"
        ),
    }
    markdown = (EVALUATION_DIR / "external_evaluation.md").read_text(encoding="utf-8")
    check(results, "1. external evaluation 状态为 COMPLETE", "状态：`COMPLETE`。" in markdown)
    check(
        results,
        "2. model training manifest hash 与 final artifact manifest 一致",
        evaluation.get("approval", {}).get("model_training_manifest_sha256")
        == sha256(FINAL_ARTIFACT_DIR / "training_manifest.json"),
    )
    check(
        results,
        "3. dataset release 和 dataset manifest hash 与训练冻结时一致",
        evaluation.get("dataset_release_id") == training.get("dataset_release_id")
        and evaluation.get("dataset_manifest_sha256")
        == training.get("dataset_manifest_sha256"),
    )
    check(
        results,
        "4. external split hash 与 release manifest 一致",
        evaluation.get("external_split")
        == {
            "path": "splits/external_test.csv",
            **release["release_artifacts"]["splits/external_test.csv"],
        },
    )
    check(results, "5. samples = 455", evaluation.get("external_split", {}).get("rows") == 455)
    check(results, "6. threshold = 0.5", evaluation.get("threshold") == 0.5)
    check(
        results,
        "7. 模型、特征、预处理、阈值均未在 external 后改变",
        evaluation.get("model_artifact") == training.get("model_artifact")
        and evaluation.get("preprocessing_artifact") == training.get("preprocessing_artifact")
        and evaluation.get("feature_manifest_sha256") == training.get("feature_manifest_sha256")
        and evaluation.get("threshold") == training.get("threshold") == 0.5,
    )
    check(
        results,
        "8. 未写 external prediction CSV",
        {item.name for item in EVALUATION_DIR.iterdir()} == EXPECTED_EVALUATION_FILES
        and not list(EVALUATION_DIR.glob("*.csv")),
    )
    digest = evaluation.get("external_prediction_digest", {})
    check(
        results,
        "9. prediction digest 已记录",
        isinstance(digest.get("sha256"), str)
        and len(digest["sha256"]) == 64
        and digest.get("rows") == 455
        and digest.get("artifact_written") is False,
    )
    source = (ROOT / "scripts" / "train_model.py").read_text(encoding="utf-8")
    lock_index = source.find('if output_dir.exists():\n        raise FileExistsError(f"external-final 已完成')
    external_read_index = source.find("external_rows = release.read_csv(PRIMARY_EXTERNAL_PATH)")
    check(
        results,
        "10. external-final repeat lock 生效",
        lock_index >= 0 and external_read_index >= 0 and lock_index < external_read_index,
    )
    changed = subprocess.run(
        ["git", "-c", "core.quotepath=false", "diff", "--name-only", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    ).stdout.splitlines()
    normalized_changed = [
        path.removeprefix(f"{ROOT.name}/") for path in changed
    ]
    check(
        results,
        "11. 当前 Git diff 只包含预期报告、manifest、lock 文件",
        all(path in ALLOWED_CHANGED_PATHS for path in normalized_changed),
    )
    external_function_start = source.find("def external_final(")
    external_function_end = source.find("\ndef main()", external_function_start)
    external_function = source[external_function_start:external_function_end]
    forbidden_feedback = (".fit(", "build_estimator(", "fit_with_train_tuning_cv(", "GridSearchCV")
    check(
        results,
        "12. external 结果没有回流到模型选择或调参代码",
        external_function_start >= 0
        and external_function_end > external_function_start
        and not any(item in external_function for item in forbidden_feedback),
    )
    return write_report(metadata, results)


def write_report(metadata: dict[str, Any], results: list[tuple[str, bool]]) -> int:
    passed = bool(results) and all(status for _, status in results)
    lines = [
        "# Final external evaluation audit",
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
            "本审核只读取既有 final artifact、external evaluation、release 元数据与 Git 元数据；不读取任何 external split 行。",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
