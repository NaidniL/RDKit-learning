#!/usr/bin/env python3
"""独立审核 v2 final artifact；只读 metadata/artifacts，不读取任何 split 行。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.v2_final_artifact import (  # noqa: E402
    MEMBER_IDS,
    V2_FINAL_ARTIFACT_FILES,
    sha256_file,
    validate_artifact_hashes,
)
from modeling.v2_final_policy import load_v2_final_policy  # noqa: E402
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


ARTIFACT_DIR = ROOT / "models" / "final_consensus_v2"
REPORT_PATH = ROOT / "reports" / "modeling" / "v2_final_artifact_audit.md"


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 不是 canonical JSON object")
    return value


def main() -> int:
    results: list[tuple[str, bool]] = []
    metadata: dict[str, Any] = {"artifact_dir": str(ARTIFACT_DIR)}
    observed = {path.name for path in ARTIFACT_DIR.iterdir()} if ARTIFACT_DIR.is_dir() else set()
    results.append(("1. v2 final artifact 目录存在", ARTIFACT_DIR.is_dir()))
    results.append(("2. artifact 文件集合严格匹配", observed == set(V2_FINAL_ARTIFACT_FILES)))
    if observed != set(V2_FINAL_ARTIFACT_FILES):
        return write_report(metadata, results)
    try:
        policy, policy_sha256 = load_v2_final_policy(ROOT / "configs" / "v2_final_policy_v1.json")
        copied_policy, copied_policy_sha256 = load_v2_final_policy(
            ARTIFACT_DIR / "v2_final_policy.json"
        )
        training = load_canonical_json(ARTIFACT_DIR / "training_manifest.json")
        consensus = load_canonical_json(ARTIFACT_DIR / "consensus_manifest.json")
        features = load_canonical_json(ARTIFACT_DIR / "feature_manifest.json")
        environment = load_canonical_json(ARTIFACT_DIR / "environment_manifest.json")
        hashes = load_canonical_json(ARTIFACT_DIR / "artifact_hashes.json")
        release = load_formal_release_metadata_without_external_reads(
            ROOT / "releases" / "dataset_assembly"
        )
    except Exception as exc:
        results.append((f"3. policy、manifest 和 release metadata 可读取：{type(exc).__name__}", False))
        return write_report(metadata, results)

    metadata.update(
        {
            "v2_final_policy_sha256": policy_sha256,
            "dataset_release_id": training.get("dataset_release_id", "missing"),
            "dataset_manifest_sha256": training.get("dataset_manifest_sha256", "missing"),
        }
    )
    results.append(("3. artifact 内 policy 与冻结 policy byte-identical", policy_sha256 == copied_policy_sha256 and policy == copied_policy))
    results.append(
        (
            "4. policy、training、consensus 和 environment manifest hashes 对齐",
            training.get("v2_final_policy_sha256") == policy_sha256
            and consensus.get("v2_final_policy_sha256") == policy_sha256
            and environment.get("v2_final_policy_sha256") == policy_sha256,
        )
    )
    expected_splits = {
        "train.csv": release.artifact_metadata("splits/primary_reproduction/train.csv"),
        "validation.csv": release.artifact_metadata("splits/primary_reproduction/validation.csv"),
    }
    results.append(
        (
            "5. formal release identity 与 train/validation artifact hashes 对齐",
            training.get("dataset_release_id") == release.release_id
            and training.get("dataset_manifest_sha256") == release.manifest_sha256
            and training.get("input_split_artifacts") == expected_splits,
        )
    )
    results.append(
        (
            "6. 三成员均在 train+validation 921 样本上重训",
            training.get("fit_split") == "train_validation"
            and training.get("refit_data")
            == {"sample_count": 921, "class_counts": {"0": 503, "1": 418}, "class_count": 2}
            and [member.get("id") for member in training.get("members", [])] == list(MEMBER_IDS),
        )
    )
    results.append(
        (
            "7. feature manifest 与三个冻结 feature sets 对齐",
            features.get("feature_manifest_version") == 1
            and {
                identifier: features.get("members", {}).get(identifier, {}).get("feature_sets")
                for identifier in MEMBER_IDS
            }
            == {
                "lightgbm_descriptors": ["rdkit_descriptors", "physicochemical"],
                "random_forest_maccs": ["maccs"],
                "random_forest_ecfp4": ["ecfp4"],
            },
        )
    )
    expected_members = {member["id"]: member for member in policy["members"]}
    members_ok = True
    try:
        for member in training["members"]:
            expected = expected_members[member["id"]]
            model_path = ARTIFACT_DIR / member["model_artifact"]["path"]
            preprocessing_path = ARTIFACT_DIR / member["preprocessing_artifact"]["path"]
            model = joblib.load(model_path)
            joblib.load(preprocessing_path)
            if (
                member["model"] != expected["model"]
                or member["feature_sets"] != expected["feature_sets"]
                or any(
                    model.get_params(deep=False).get(key) != value
                    for key, value in expected["model_params"].items()
                )
                or member["model_artifact"]
                != {"path": model_path.name, **{"bytes": model_path.stat().st_size, "sha256": sha256_file(model_path)}}
                or member["preprocessing_artifact"]
                != {
                    "path": preprocessing_path.name,
                    **{"bytes": preprocessing_path.stat().st_size, "sha256": sha256_file(preprocessing_path)},
                }
            ):
                members_ok = False
    except Exception:
        members_ok = False
    results.append(("8. 三成员参数、模型及 preprocessing artifacts 可复核", members_ok))
    results.append(
        (
            "9. consensus rule、output contract 和保守 AD policy 对齐",
            consensus.get("member_order") == list(MEMBER_IDS)
            and consensus.get("threshold") == 0.5
            and consensus.get("rule")
            == {
                "positive": policy["consensus_rule"]["positive"],
                "negative": policy["consensus_rule"]["negative"],
                "otherwise": policy["consensus_rule"]["otherwise"],
            }
            and consensus.get("output_contract") == policy["output_contract"]
            and consensus.get("applicability_domain") == policy["applicability_domain"],
        )
    )
    try:
        validate_artifact_hashes(ARTIFACT_DIR, hashes)
        hashes_ok = True
    except Exception:
        hashes_ok = False
    results.append(("10. 非自引用 artifact hashes 完整匹配", hashes_ok))
    results.append(
        (
            "11. 不含 predictions/metrics，所有 manifest external_access=denied",
            training.get("prediction_artifact_written") is False
            and not ({"predictions", "metrics", "external_results", "validation_results"} & set(training))
            and environment.get("external_access") == "denied"
            and "external_access=denied" in (ARTIFACT_DIR / "training.log").read_text(encoding="utf-8"),
        )
    )
    return write_report(metadata, results)


def write_report(metadata: dict[str, Any], results: list[tuple[str, bool]]) -> int:
    passed = bool(results) and all(status for _, status in results)
    lines = ["# v2 final-artifact audit", "", f"状态：`{'PASS' if passed else 'FAIL'}`。", ""]
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
            "本审核只读取 final artifacts、policy 与 formal release metadata；不读取任何 split 行或 external 数据。",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
