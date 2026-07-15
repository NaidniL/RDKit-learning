#!/usr/bin/env python3
"""只读审核 v2 development-only consensus 输出。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


CONFIG_PATH = ROOT / "configs" / "consensus_v2_development_v1.json"
OUTPUT_DIR = ROOT / "reports" / "modeling" / "v2_consensus_development_v1"
REPORT_PATH = ROOT / "reports" / "modeling" / "v2_consensus_development_audit.md"


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
    try:
        config = load_canonical_json(CONFIG_PATH)
        manifest = load_canonical_json(OUTPUT_DIR / "consensus_development_manifest.json")
        pointer = load_canonical_json(ROOT / "releases" / "dataset_assembly" / "current_release.json")
        release = load_canonical_json(
            ROOT / "releases" / "dataset_assembly" / pointer["manifest_path"]
        )
    except Exception as exc:
        check(results, f"输入可读取：{type(exc).__name__}", False)
        return write_report({}, results)
    metadata = {
        "config_sha256": manifest.get("config_sha256", "missing"),
        "dataset_release_id": manifest.get("dataset_release_id", "missing"),
        "dataset_manifest_sha256": manifest.get("dataset_manifest_sha256", "missing"),
        "consensus_coverage": manifest.get("consensus_validation_result", {}).get("coverage", "missing"),
    }
    check(results, "1. config SHA-256 与 canonical frozen config 一致", manifest.get("config_sha256") == sha256(CONFIG_PATH))
    check(results, "2. status 是 frozen development-only 且 external_access=denied", config.get("status") == "FROZEN_DEVELOPMENT_ONLY" and config.get("external_access") == "denied" and manifest.get("external_access") == "denied")
    check(results, "3. 只使用当前 formal release 的 train/validation metadata", manifest.get("dataset_release_id") == pointer.get("release_id") and manifest.get("dataset_manifest_sha256") == pointer.get("manifest_sha256") and manifest.get("split_artifacts") == {"train.csv": release["release_artifacts"]["splits/primary_reproduction/train.csv"], "validation.csv": release["release_artifacts"]["splits/primary_reproduction/validation.csv"]})
    check(results, "4. 模型集合和顺序已冻结", [item.get("id") for item in config.get("models", [])] == ["lightgbm_descriptors", "random_forest_maccs", "random_forest_ecfp4"])
    consensus = manifest.get("consensus_validation_result", {})
    check(results, "5. coverage 与 inconclusive counts 自洽", consensus.get("covered_count", 0) + consensus.get("inconclusive_count", 0) == 185 and consensus.get("covered_count", 0) == consensus.get("positive_call_count", 0) + consensus.get("negative_call_count", 0) and consensus.get("coverage") == consensus.get("covered_count", 0) / 185)
    check(results, "6. 仅有批准的 aggregate 输出文件", {item.name for item in OUTPUT_DIR.iterdir()} == {"consensus_development.md", "consensus_development_manifest.json"})
    check(results, "7. 未写样本级 prediction artifact", manifest.get("prediction_artifact_written") is False and not list(OUTPUT_DIR.glob("*.csv")))
    source = (ROOT / "scripts" / "run_v2_consensus_development.py").read_text(encoding="utf-8")
    check(results, "8. consensus runner 未调用 external split loader", "load_release_split" not in source and "external_final" not in source and "load_train_validation_splits" in source)
    check(results, "9. external evaluation 仍未由此 config 授权", config.get("final_evaluation") == "not_authorized_by_this_development_config")
    return write_report(metadata, results)


def write_report(metadata: dict[str, Any], results: list[tuple[str, bool]]) -> int:
    passed = bool(results) and all(status for _, status in results)
    lines = ["# v2 development-only consensus audit", "", f"状态：`{'PASS' if passed else 'FAIL'}`。", "", "## Immutable metadata", ""]
    lines.extend(f"- {key}: `{value}`" for key, value in metadata.items())
    lines.extend(["", "## Checks", "", "| # | Check | Status |", "|---:|---|---|"])
    lines.extend(f"| {index} | {label} | {'PASS' if status else 'FAIL'} |" for index, (label, status) in enumerate(results, start=1))
    lines.extend(["", "本审核只读取 config、development aggregate outputs 与 release 元数据；不读取任何 external split 行。", ""])
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
