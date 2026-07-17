#!/usr/bin/env python3
"""只读审核冻结的 v2 final policy；不读取任何 external split。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.v2_final_policy import (  # noqa: E402
    MEMBER_ORDER,
    load_v2_final_policy,
    sha256_file,
)


POLICY_PATH = ROOT / "configs" / "v2_final_policy_v1.json"
REPORT_PATH = ROOT / "reports" / "modeling" / "v2_final_policy_audit.md"


def main() -> int:
    results: list[tuple[str, bool]] = []
    try:
        policy, policy_sha256 = load_v2_final_policy(POLICY_PATH)
        release = load_formal_release_metadata_without_external_reads(
            ROOT / "releases" / "dataset_assembly"
        )
    except Exception as exc:
        results.append((f"可读取并验证 policy/release metadata：{type(exc).__name__}", False))
        return write_report({}, results)

    data = policy["data_identity"]
    results.append(
        (
            "1. policy 绑定当前 formal release identity",
            data["formal_release_id"] == release.release_id
            and data["dataset_manifest_sha256"] == release.manifest_sha256,
        )
    )
    results.append(
        (
            "2. train/validation artifact metadata 与 release 一致",
            data["split_artifacts"]
            == {
                "train.csv": release.artifact_metadata("splits/primary_reproduction/train.csv"),
                "validation.csv": release.artifact_metadata(
                    "splits/primary_reproduction/validation.csv"
                ),
            },
        )
    )
    results.append(
        (
            "3. final refit 固定为 736 + 185 = 921 个 development 样本",
            data["final_refit"]["sample_count"]
            == data["split_artifacts"]["train.csv"]["rows"]
            + data["split_artifacts"]["validation.csv"]["rows"],
        )
    )
    results.append(
        (
            "4. 三成员顺序、0.5 unanimity 和三路输出已冻结",
            policy["consensus_rule"]["member_order"] == list(MEMBER_ORDER)
            and policy["consensus_rule"]["threshold"] == 0.5,
        )
    )
    results.append(
        (
            "5. output contract hash 与冻结文件一致",
            policy["output_contract"]["sha256"]
            == sha256_file(ROOT / "configs" / "v2_output_contract_v1.json"),
        )
    )
    results.append(
        (
            "6. development config、诊断报告和审核报告均已绑定",
            policy["prerequisites"]
            == {
                "development_audit_report_sha256": sha256_file(
                    ROOT / "reports" / "modeling" / "v2_consensus_development_audit.md"
                ),
                "development_config_sha256": sha256_file(
                    ROOT / "configs" / "consensus_v2_development_v1.json"
                ),
                "development_diagnostics_report_sha256": sha256_file(
                    ROOT / "reports" / "modeling" / "v2_selective_prediction.md"
                ),
            },
        )
    )
    results.append(
        (
            "7. 保守 AD 仅报告，不改变 prediction",
            policy["applicability_domain"]["call_effect"] == "none"
            and policy["applicability_domain"]["reporting_only"] is True,
        )
    )
    results.append(
        (
            "8. v1 primary external 被禁止；新 external 未获此 policy 授权",
            policy["external_evaluation"]["v1_primary_external"] == "prohibited"
            and policy["external_evaluation"]["status"] == "not_authorized_by_this_policy",
        )
    )
    results.append(
        (
            "9. coverage、covered metrics 和错误富集成功标准已冻结",
            policy["metrics"]["success_criteria"]["coverage_minimum"] == 0.65
            and policy["metrics"]["success_criteria"]["inconclusive_mean_member_error_rate_vs_covered"]
            == "greater",
        )
    )
    metadata = {
        "policy_sha256": policy_sha256,
        "dataset_release_id": release.release_id,
        "dataset_manifest_sha256": release.manifest_sha256,
        "external_access": policy["external_evaluation"]["status"],
    }
    return write_report(metadata, results)


def write_report(metadata: dict[str, object], results: list[tuple[str, bool]]) -> int:
    passed = bool(results) and all(status for _, status in results)
    lines = ["# v2 final-policy audit", "", f"状态：`{'PASS' if passed else 'FAIL'}`。", ""]
    lines.extend(["## Immutable metadata", ""])
    lines.extend(f"- {name}: `{value}`" for name, value in metadata.items())
    lines.extend(["", "## Checks", "", "| # | Check | Status |", "|---:|---|---|"])
    lines.extend(
        f"| {index} | {label} | {'PASS' if status else 'FAIL'} |"
        for index, (label, status) in enumerate(results, start=1)
    )
    lines.extend(
        [
            "",
            "本审核仅读取 policy、development prerequisite artifacts 和 formal release metadata；未读取任何 external split。",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
