#!/usr/bin/env python3
"""审核 v2 external 评估的 preflight 或已完成的一次性评估元数据。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.v2_final_artifact import sha256_file  # noqa: E402
from modeling.v2_final_policy import load_v2_final_policy  # noqa: E402
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


ARTIFACT_DIR = ROOT / "models" / "final_consensus_v2"
EVALUATION_DIR = ROOT / "reports" / "modeling" / "v2_external_evaluation_v1"
REPORT_PATH = ROOT / "reports" / "modeling" / "v2_external_evaluation_audit.md"
EXPECTED_EVALUATION_FILES = {"external_evaluation.md", "external_evaluation_manifest.json"}
AUTHORIZATION_PATH = ROOT / "configs" / "v2_external_evaluation_ntp_authorization_v1.json"
CANDIDATE_RELEASE_MANIFEST_PATH = (
    ROOT / "data" / "interim" / "v2_external_ntp_candidate_release_manifest.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="只有 external evaluation artifact 已存在且通过完整审计时才返回 0",
    )
    return parser.parse_args()


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 不是 canonical JSON object")
    return value


def has_pass_report(path: Path) -> bool:
    return path.is_file() and "状态：`PASS`。" in path.read_text(encoding="utf-8")


def preflight_checks() -> tuple[dict[str, Any], list[tuple[str, bool]]]:
    """Verify that no external read/evaluation is authorized or already present."""

    results: list[tuple[str, bool]] = []
    policy, policy_sha256 = load_v2_final_policy(ROOT / "configs" / "v2_final_policy_v1.json")
    metadata = {
        "mode": "PRE_EXTERNAL_READY",
        "v2_final_policy_sha256": policy_sha256,
        "external_evaluation_directory": str(EVALUATION_DIR),
    }
    results.append(
        (
            "1. policy 明确禁止 v1 primary external 且未授权新 external",
            policy["external_evaluation"]
            == {
                "new_external_manifest": "must_be_bound_and_hashed_before_any_read",
                "policy_change_after_new_external_read": "prohibited",
                "status": "not_authorized_by_this_policy",
                "v1_primary_external": "prohibited",
            },
        )
    )
    results.append(
        (
            "2. policy audit 与 final-artifact audit 均已通过",
            has_pass_report(ROOT / "reports" / "modeling" / "v2_final_policy_audit.md")
            and has_pass_report(ROOT / "reports" / "modeling" / "v2_final_artifact_audit.md"),
        )
    )
    results.append(
        (
            "3. final artifact policy hash 与当前冻结 policy 一致",
            ARTIFACT_DIR.is_dir()
            and sha256_file(ARTIFACT_DIR / "v2_final_policy.json") == policy_sha256,
        )
    )
    results.append(
        (
            "4. 尚无 external evaluation output；不会重用 v1 external",
            not EVALUATION_DIR.exists(),
        )
    )
    results.append(
        (
            "5. future external 必须先有独立 manifest/hash，且 policy 之后不得修改",
            policy["external_evaluation"]["new_external_manifest"]
            == "must_be_bound_and_hashed_before_any_read"
            and policy["external_evaluation"]["policy_change_after_new_external_read"]
            == "prohibited",
        )
    )
    return metadata, results


def complete_checks() -> tuple[dict[str, Any], list[tuple[str, bool]]]:
    """Audit future external evaluation metadata only; never open external rows."""

    policy, policy_sha256 = load_v2_final_policy(ROOT / "configs" / "v2_final_policy_v1.json")
    training = load_canonical_json(ARTIFACT_DIR / "training_manifest.json")
    evaluation = load_canonical_json(EVALUATION_DIR / "external_evaluation_manifest.json")
    authorization_config = load_canonical_json(AUTHORIZATION_PATH)
    candidate_release = load_canonical_json(CANDIDATE_RELEASE_MANIFEST_PATH)
    markdown = (EVALUATION_DIR / "external_evaluation.md").read_text(encoding="utf-8")
    metadata = {
        "mode": "COMPLETE_EXTERNAL_EVALUATION",
        "v2_final_policy_sha256": policy_sha256,
        "external_evaluation_id": evaluation.get("external_evaluation_id", "missing"),
    }
    results: list[tuple[str, bool]] = []
    results.append(
        (
            "1. output 文件集合固定且没有样本级 prediction CSV",
            {path.name for path in EVALUATION_DIR.iterdir()} == EXPECTED_EVALUATION_FILES
            and not list(EVALUATION_DIR.glob("*.csv")),
        )
    )
    results.append(
        (
            "2. NTP candidate identity、独立授权、绑定 hashes 和预先创建的输出锁完整",
            isinstance(evaluation.get("external_dataset"), dict)
            and isinstance(evaluation.get("authorization"), dict)
            and authorization_config
            == {
                "authorization_id": "v2_external_evaluation_ntp_v1",
                "candidate_release_manifest": {
                    "path": "data/interim/v2_external_ntp_candidate_release_manifest.json",
                    "sha256": sha256_file(CANDIDATE_RELEASE_MANIFEST_PATH),
                },
                "execution": {
                    "output_directory": "reports/modeling/v2_external_evaluation_v1",
                    "prediction_csv_prohibited": True,
                    "repeat_execution_prohibited": True,
                    "single_external_read": True,
                },
                "final_artifact": {
                    "artifact_hashes_sha256": sha256_file(ARTIFACT_DIR / "artifact_hashes.json"),
                    "training_manifest_sha256": sha256_file(ARTIFACT_DIR / "training_manifest.json"),
                },
                "policy": {"sha256": policy_sha256, "status": "FROZEN_FINAL_POLICY_PRE_EXTERNAL"},
                "status": "FROZEN_ONE_SHOT_EXTERNAL_EVALUATION_AUTHORIZED",
                "v1_primary_external": "prohibited",
                "version": 1,
            }
            and evaluation.get("authorization", {})
            == {
                "authorization_config_sha256": sha256_file(AUTHORIZATION_PATH),
                "new_external_manifest_sha256": sha256_file(CANDIDATE_RELEASE_MANIFEST_PATH),
                "v2_final_policy_sha256": policy_sha256,
            }
            and evaluation.get("external_dataset", {})
            == {
                "candidate_id": candidate_release.get("candidate_id"),
                "candidate_csv_sha256": candidate_release.get("candidate_csv", {}).get("sha256"),
                "candidate_release_manifest_sha256": sha256_file(CANDIDATE_RELEASE_MANIFEST_PATH),
                "sample_count": candidate_release.get("candidate_rows"),
            }
            and evaluation.get("output_directory_lock")
            == {"created_before_external_read": True, "repeat_execution_prevented": True},
        )
    )
    overlap = evaluation.get("overlap_audit", {})
    results.append(
        (
            "3. exact/connectivity/tautomer overlap 均为零",
            overlap == {"connectivity_overlap_count": 0, "exact_overlap_count": 0, "tautomer_overlap_count": 0},
        )
    )
    results.append(
        (
            "4. final artifact、policy 和 member hashes 在 external 后未改变",
            evaluation.get("final_artifact")
            == {
                "artifact_hashes_sha256": sha256_file(ARTIFACT_DIR / "artifact_hashes.json"),
                "training_manifest_sha256": sha256_file(ARTIFACT_DIR / "training_manifest.json"),
                "v2_final_policy_sha256": policy_sha256,
            }
            and training.get("v2_final_policy_sha256") == policy_sha256,
        )
    )
    diagnostics = evaluation.get("preregistered_diagnostics", [])
    results.append(
        (
            "5. 仅按预注册方式报告 tautomer/scaffold/similarity，AD 不改变 call",
            diagnostics
            == [
                "tautomer_sensitivity_descriptive",
                "scaffold_stratified_metrics",
                "ecfp4_similarity_stratified_metrics",
            ]
            and evaluation.get("applicability_domain_call_effect") == "none",
        )
    )
    prediction_digest = evaluation.get("external_prediction_digest", {})
    results.append(
        (
            "6. 仅保留 prediction digest，不保留样本级预测",
            prediction_digest.get("artifact_written") is False
            and isinstance(prediction_digest.get("sha256"), str)
            and len(prediction_digest["sha256"]) == 64,
        )
    )
    results.append(
        (
            "7. external 结果未触发模型或规则修改",
            evaluation.get("post_evaluation_model_or_policy_change") is False
            and "状态：`COMPLETE`。" in markdown,
        )
    )
    results.append(
        (
            "8. 所需 aggregate diagnostics、同 covered subset 的 v1 比较和预注册阈值 readout 已记录",
            isinstance(evaluation.get("summary"), dict)
            and isinstance(evaluation.get("members"), dict)
            and isinstance(evaluation.get("similarity_strata"), list)
            and isinstance(evaluation.get("scaffold_strata"), list)
            and evaluation.get("tautomer_diagnostic", {}).get("development_tautomer_overlap_count") == 0
            and isinstance(evaluation.get("v1_same_covered_subset"), dict)
            and isinstance(evaluation.get("success_criteria"), dict),
        )
    )
    return metadata, results


def write_report(
    metadata: dict[str, Any], results: list[tuple[str, bool]], *, status: str
) -> int:
    lines = ["# v2 external-evaluation audit", "", f"状态：`{status}`。", ""]
    lines.extend(["## Immutable metadata", ""])
    lines.extend(f"- {name}: `{value}`" for name, value in metadata.items())
    lines.extend(["", "## Checks", "", "| # | Check | Status |", "|---:|---|---|"])
    lines.extend(
        f"| {index} | {label} | {'PASS' if passed else 'FAIL'} |"
        for index, (label, passed) in enumerate(results, start=1)
    )
    lines.extend(
        [
            "",
            "本审核只读取 policy、final artifacts 和 future external-evaluation metadata；不读取任何 external split 行。",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return 0 if results and all(passed for _, passed in results) else 1


def main() -> int:
    args = parse_args()
    if not EVALUATION_DIR.exists():
        try:
            metadata, results = preflight_checks()
        except Exception as exc:
            return write_report({"mode": "PRE_EXTERNAL_READY"}, [(type(exc).__name__, False)], status="FAIL")
        status = "PRE_EXTERNAL_READY" if all(passed for _, passed in results) else "FAIL"
        exit_code = write_report(metadata, results, status=status)
        return 1 if args.require_complete else exit_code
    try:
        metadata, results = complete_checks()
    except Exception as exc:
        return write_report({"mode": "COMPLETE_EXTERNAL_EVALUATION"}, [(type(exc).__name__, False)], status="FAIL")
    return write_report(metadata, results, status="PASS" if all(passed for _, passed in results) else "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
