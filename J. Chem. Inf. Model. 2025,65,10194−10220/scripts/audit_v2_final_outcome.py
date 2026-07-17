#!/usr/bin/env python3
"""Audit the immutable aggregate-only v2 outcome release without external reads."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


SOURCE_DIR = ROOT / "reports" / "modeling" / "v2_external_evaluation_v1"
FINAL_DIR = ROOT / "reports" / "modeling" / "final_consensus_v2_evaluation_v1"
AUDIT_PATH = FINAL_DIR / "complete_audit.md"
EXPECTED = {"external_evaluation.md", "outcome_classification.json", "evaluation_manifest.json", "complete_audit.md"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 必须是 canonical JSON object")
    return value


def audit_checks() -> list[tuple[str, bool]]:
    source_manifest = SOURCE_DIR / "external_evaluation_manifest.json"
    source_report = SOURCE_DIR / "external_evaluation.md"
    source = load_canonical_json(source_manifest)
    outcome = load_canonical_json(FINAL_DIR / "outcome_classification.json")
    manifest = load_canonical_json(FINAL_DIR / "evaluation_manifest.json")
    return [
        ("1. final release 的 pre-audit 文件集合固定", {path.name for path in FINAL_DIR.iterdir()} == EXPECTED - {"complete_audit.md"}),
        ("2. source external report 与 manifest hashes 已绑定", manifest.get("source_external_evaluation") == {"manifest_path": "reports/modeling/v2_external_evaluation_v1/external_evaluation_manifest.json", "manifest_sha256": sha256_file(source_manifest), "report_path": "reports/modeling/v2_external_evaluation_v1/external_evaluation.md", "report_sha256": sha256_file(source_report)}),
        ("3. outcome 机械反映冻结 criteria：PARTIAL_SUCCESS 且仅 sensitivity 未通过", outcome.get("status") == "PARTIAL_SUCCESS" and outcome.get("coverage_pass") is True and outcome.get("covered_mcc_pass") is True and outcome.get("error_enrichment_pass") is True and outcome.get("specificity_pass") is True and outcome.get("sensitivity_pass") is False and outcome.get("overall_success") is False and outcome.get("failure_reason") == "covered sensitivity 0.625000 < preregistered minimum 0.650000"),
        ("4. Wilson interval 仅描述性，且来自 locked covered confusion", outcome.get("confidence_intervals_descriptive_only", {}).get("covered_sensitivity_wilson", {}).get("successes") == source["summary"]["consensus_covered"]["confusion"]["true_positive"] and outcome.get("confidence_intervals_descriptive_only", {}).get("covered_sensitivity_wilson", {}).get("total") == source["summary"]["consensus_covered"]["confusion"]["true_positive"] + source["summary"]["consensus_covered"]["confusion"]["false_negative"]),
        ("5. final tag 不夸大结果，且 freeze scope 不读取 external rows", manifest.get("final_tag") == "final-consensus-v2-external-partial-v1" and manifest.get("freeze_scope") == "aggregate_only; no external candidate rows read"),
    ]


def main() -> int:
    if AUDIT_PATH.exists():
        raise FileExistsError("complete audit 已存在；拒绝改写 final release")
    checks = audit_checks()
    passed = all(value for _, value in checks)
    lines = ["# v2 final outcome complete audit", "", f"状态：`{'PASS' if passed else 'FAIL'}`。", "", "| # | Check | Status |", "|---:|---|---|"]
    lines.extend(f"| {index} | {label} | {'PASS' if value else 'FAIL'} |" for index, (label, value) in enumerate(checks, 1))
    lines.extend(["", "本审核只读取已锁定的 external aggregate manifest/report 与 final release 文件；不读取 candidate CSV 或任一 external 行。", ""])
    AUDIT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
