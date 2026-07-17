#!/usr/bin/env python3
"""Freeze the aggregate-only final v2 outcome; never open external candidate rows."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


SOURCE_DIR = ROOT / "reports" / "modeling" / "v2_external_evaluation_v1"
SOURCE_MANIFEST = SOURCE_DIR / "external_evaluation_manifest.json"
SOURCE_REPORT = SOURCE_DIR / "external_evaluation.md"
FINAL_DIR = ROOT / "reports" / "modeling" / "final_consensus_v2_evaluation_v1"
OUTCOME_NAME = "outcome_classification.json"
MANIFEST_NAME = "evaluation_manifest.json"
REPORT_NAME = "external_evaluation.md"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 必须是 canonical JSON object")
    return value


def wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> dict[str, float | int]:
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("Wilson interval requires 0 <= successes <= total")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = z * ((proportion * (1 - proportion) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return {"confidence_level": 0.95, "estimate": proportion, "lower": center - radius, "successes": successes, "total": total, "upper": center + radius}


def main() -> int:
    if FINAL_DIR.exists():
        raise FileExistsError("v2 final evaluation release 已存在；拒绝重冻结")
    source = load_canonical_json(SOURCE_MANIFEST)
    source_report = SOURCE_REPORT.read_text(encoding="utf-8")
    if "状态：`COMPLETE`。" not in source_report:
        raise ValueError("source external report 未完成")
    summary = source.get("summary", {})
    covered = summary.get("consensus_covered", {})
    confusion = covered.get("confusion", {})
    metrics = covered.get("metrics", {})
    sensitivity = wilson_interval(int(confusion["true_positive"]), int(confusion["true_positive"] + confusion["false_negative"]))
    specificity = wilson_interval(int(confusion["true_negative"]), int(confusion["true_negative"] + confusion["false_positive"]))
    success = source.get("success_criteria", {})
    comparator = source.get("v1_same_covered_subset", {})
    required = {
        "coverage_pass": bool(success.get("coverage_minimum_met")),
        "covered_mcc_pass": bool(comparator.get("requirement_met")),
        "error_enrichment_pass": bool(success.get("inconclusive_error_enriched")),
        "sensitivity_pass": bool(success.get("covered_sensitivity_minimum_met")),
        "specificity_pass": bool(success.get("covered_specificity_minimum_met")),
    }
    overall_success = all(required.values())
    if overall_success:
        status, tag, failure_reason = "FULL_SUCCESS", "final-consensus-v2-external-success-v1", None
    else:
        status, tag = "PARTIAL_SUCCESS", "final-consensus-v2-external-partial-v1"
        failure_reason = "covered sensitivity 0.625000 < preregistered minimum 0.650000"
    outcome = {
        "classification_version": 1,
        "confidence_intervals_descriptive_only": {"covered_sensitivity_wilson": sensitivity, "covered_specificity_wilson": specificity},
        "covered_mcc_pass": required["covered_mcc_pass"],
        "coverage_pass": required["coverage_pass"],
        "error_enrichment_pass": required["error_enrichment_pass"],
        "failure_reason": failure_reason,
        "final_tag": tag,
        "overall_success": overall_success,
        "sensitivity_pass": required["sensitivity_pass"],
        "specificity_pass": required["specificity_pass"],
        "status": status,
    }
    final_report = source_report + "\n## Frozen final outcome\n\n"
    final_report += "- Final status: `PARTIAL_SUCCESS`。\n"
    final_report += "- 预注册判定不因区间而改变：coverage、同 covered subset MCC、错误富集和 specificity 通过；covered sensitivity 不通过（`0.625000 < 0.650000`）。\n"
    final_report += f"- Covered sensitivity Wilson 95% CI (5/8): `[{sensitivity['lower']:.6f}, {sensitivity['upper']:.6f}]`；covered specificity Wilson 95% CI (23/24): `[{specificity['lower']:.6f}, {specificity['upper']:.6f}]`。区间仅描述小样本不稳定性，不能替代已冻结点估计门槛。\n"
    final_report += "- 因此不得称为‘验证成功’、‘优于 v1’或‘可用于致癌物筛查’；准确表述是：独立 external 验证部分成功。\n"
    final_report += "\n## Inconclusive-member aggregate errors\n\n| Member | Full errors | Covered errors | Inconclusive errors |\n|---|---:|---:|---:|\n"
    for member, values in source["members"].items():
        full = values["full"]["confusion"]
        covered_member = values["covered"]["confusion"]
        full_errors = full["false_positive"] + full["false_negative"]
        covered_errors = covered_member["false_positive"] + covered_member["false_negative"]
        final_report += f"| {member} | {full_errors} | {covered_errors} | {full_errors - covered_errors} |\n"
    manifest = {
        "evaluation_manifest_version": 1,
        "final_outcome_classification_sha256": hashlib.sha256(canonical_json_bytes(outcome)).hexdigest(),
        "final_tag": tag,
        "freeze_scope": "aggregate_only; no external candidate rows read",
        "source_external_evaluation": {
            "manifest_path": "reports/modeling/v2_external_evaluation_v1/external_evaluation_manifest.json",
            "manifest_sha256": sha256_file(SOURCE_MANIFEST),
            "report_path": "reports/modeling/v2_external_evaluation_v1/external_evaluation.md",
            "report_sha256": sha256_file(SOURCE_REPORT),
        },
        "status": "FROZEN_FINAL_V2_OUTCOME",
    }
    FINAL_DIR.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".final_v2_outcome.", dir=FINAL_DIR.parent))
    try:
        (temporary / OUTCOME_NAME).write_bytes(canonical_json_bytes(outcome))
        (temporary / MANIFEST_NAME).write_bytes(canonical_json_bytes(manifest))
        (temporary / REPORT_NAME).write_text(final_report, encoding="utf-8")
        os.replace(temporary, FINAL_DIR)
    except Exception:
        for path in temporary.iterdir():
            path.unlink()
        temporary.rmdir()
        raise
    print(json.dumps({"final_tag": tag, "overall_success": overall_success, "status": status}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
