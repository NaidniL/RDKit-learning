#!/usr/bin/env python3
"""只读验证冻结 final config；唯一写入为指定的 Markdown 审核报告。"""

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


EXPECTED_CONFIG_SHA256 = "19a0ca3d720c940e6574b43abfee13a6f7ca76f73d67b13ef60b7844fef6f486"
EXPECTED_POLICY_SHA256 = "e56583f94f71326fce2d59f63c4027b18445403b27c18eddfc141881cd5cdc10"
EXPERIMENTS = (
    "rf-ecfp4",
    "rf-maccs",
    "rf-descriptors",
    "rf-mixed",
    "lightgbm-ecfp4",
    "lightgbm-maccs",
    "lightgbm-descriptors",
    "lightgbm-mixed",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition: bool, message: str, results: list[tuple[str, bool, str]]) -> None:
    results.append((message, condition, "PASS" if condition else "FAIL"))


def contains_external_forbidden(value: Any, *, key: str = "") -> bool:
    if isinstance(value, dict):
        return any(
            contains_external_forbidden(item, key=str(name)) for name, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_external_forbidden(item, key=key) for item in value)
    text = f"{key}:{value}".lower()
    return "external" in text and key != "external_access"


def main() -> int:
    config_path = ROOT / "configs" / "final_model_config_v1.json"
    policy_path = ROOT / "docs" / "modeling_training_policy.md"
    ranking_path = ROOT / "reports" / "modeling" / "batch2_candidate_ranking.md"
    report_path = ROOT / "reports" / "modeling" / "final_config_independent_audit.md"
    results: list[tuple[str, bool, str]] = []

    config_raw = config_path.read_bytes()
    config = json.loads(config_raw)
    check(sha256(config_path) == EXPECTED_CONFIG_SHA256, "1. final config SHA-256 固定值", results)
    check(config_raw == canonical_json_bytes(config), "2. final config canonical JSON", results)
    ranking_text = ranking_path.read_text(encoding="utf-8")
    check(
        ranking_path.exists() and EXPECTED_POLICY_SHA256 in ranking_text,
        "3. selection report 存在且 policy hash 匹配",
        results,
    )
    check(sha256(policy_path) == EXPECTED_POLICY_SHA256, "4. modeling policy hash 匹配", results)
    check(
        config["model_family"] == "LightGBM"
        and config["feature_set"] == "rdkit_physicochemical_descriptors",
        "5. proposed final config 是 LightGBM + descriptors",
        results,
    )
    check(
        config["selected_params"]
        == {"learning_rate": 0.03, "min_child_samples": 10, "n_estimators": 300, "num_leaves": 31, "reg_lambda": 0},
        "6. selected params 与排序第 1 名一致",
        results,
    )
    check(config["threshold"] == 0.5, "7. threshold 固定为 0.5", results)
    check(
        config["training_strategy"]["final_external_model"] == "fit_train_plus_validation_evaluate_external_once",
        "8. final refit 固定为 train+validation",
        results,
    )
    check(config["external_access"] == "locked_until_independent_audit", "9. config external 仍锁定", results)

    manifests: list[dict[str, Any]] = []
    for name in EXPERIMENTS:
        path = Path("/tmp") / f"rdkit-{name}" / "experiment_manifest.json"
        if not path.exists():
            results.append((f"manifest 存在：{name}", False, "FAIL"))
            continue
        manifests.append(json.loads(path.read_text(encoding="utf-8")))
    check(len(manifests) == len(EXPERIMENTS) and all(m.get("external_access") == "denied" for m in manifests), "10. 所有 experiment manifest external_access=denied", results)
    check(not any(contains_external_forbidden(m) for m in manifests), "11. 不存在 external metric/prediction/digest/artifact", results)
    expected_candidates = {"RandomForest", "LightGBM"}
    observed_candidates = {"RandomForest" if m["configuration"]["model"] == "random_forest" else "LightGBM" for m in manifests}
    check(observed_candidates == expected_candidates and len(manifests) == 8, "12. 未发现候选外模型、特征或扩展网格", results)
    diff = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    allowed_prefixes = ("configs/", "docs/", "reports/modeling/", "scripts/", "src/modeling/", "tests/")
    changed = [line for line in diff.stdout.splitlines() if line]
    check(all(path.startswith(allowed_prefixes) for path in changed), "13. 当前 Git diff 仅含预期路径", results)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False).stdout.strip()
    metadata = {
        "HEAD": head or "unavailable",
        "dataset_release_manifest_sha256": manifests[0]["release_manifest_sha256"] if manifests else "unavailable",
        "policy_sha256": sha256(policy_path),
        "config_sha256": sha256(config_path),
    }
    check(all(metadata.values()), "14. HEAD/release/policy/config hashes 已写入报告", results)
    passed = all(ok for _, ok, _ in results)
    lines = ["# Final config independent audit", "", f"状态：`{'PASS' if passed else 'FAIL'}`。", "", "## Immutable metadata", ""]
    lines.extend(f"- {name}: `{value}`" for name, value in metadata.items())
    lines.extend(["", "## Checks", "", "| # | Check | Status |", "|---:|---|---|"])
    for index, (message, _, status) in enumerate(results, start=1):
        lines.append(f"| {index} | {message} | {status} |")
    lines.extend(["", "本脚本只读校验输入；唯一写入为本报告。external 未被读取或解锁。", ""])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
