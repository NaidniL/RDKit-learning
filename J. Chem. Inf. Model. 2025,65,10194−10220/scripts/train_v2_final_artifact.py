#!/usr/bin/env python3
"""按冻结 v2 policy 重训三成员 final artifact；external 永不读取。"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import lightgbm  # noqa: E402
import numpy as np  # noqa: E402
import rdkit  # noqa: E402
import sklearn  # noqa: E402

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.experiment_manifest import write_json_artifact  # noqa: E402
from modeling.experiment_config import ExperimentConfig  # noqa: E402
from modeling.featurizers import feature_manifest, featurize_smiles  # noqa: E402
from modeling.split_loader import load_train_validation_splits  # noqa: E402
from modeling.train_baseline import build_estimator  # noqa: E402
from modeling.v2_final_artifact import (  # noqa: E402
    MEMBER_IDS,
    V2_FINAL_ARTIFACT_FILES,
    build_artifact_hashes,
    build_consensus_manifest,
    build_training_manifest,
    file_metadata,
    member_artifact_paths,
)
from modeling.v2_final_policy import load_v2_final_policy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy", type=Path, default=ROOT / "configs" / "v2_final_policy_v1.json"
    )
    parser.add_argument(
        "--releases-root", type=Path, default=ROOT / "releases" / "dataset_assembly"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "models" / "final_consensus_v2"
    )
    parser.add_argument(
        "--no-external",
        action="store_true",
        required=True,
        help="必须显式确认训练不读取任何 external split",
    )
    return parser.parse_args()


def runtime_signature() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scikit_learn": sklearn.__version__,
        "rdkit": rdkit.__version__,
        "lightgbm": lightgbm.__version__,
    }


def code_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def prepare_output(output_dir: Path) -> Path:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"v2 final artifact 已存在，拒绝覆盖：{output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=".final_consensus_v2.", dir=output_dir.parent))


def _member_record(
    *,
    spec: dict[str, Any],
    model_path: Path,
    preprocessing_path: Path,
    matrix: Any,
    model_params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": spec["id"],
        "model": spec["model"],
        "feature_sets": list(spec["feature_sets"]),
        "feature_count": len(matrix.feature_names),
        "feature_versions": {item.name: item.version for item in matrix.specs},
        "resolved_model_params": model_params,
        "preprocessing": dict(spec["preprocessing"]),
        "probability_output": spec["probability_output"],
        "model_artifact": {"path": model_path.name, **file_metadata(model_path)},
        "preprocessing_artifact": {
            "path": preprocessing_path.name,
            **file_metadata(preprocessing_path),
        },
    }


def main() -> int:
    args = parse_args()
    if not args.no_external:
        raise PermissionError("必须使用 --no-external")
    policy, policy_sha256 = load_v2_final_policy(args.policy)
    if args.output_dir.resolve() != (ROOT / "models" / "final_consensus_v2").resolve():
        raise PermissionError("v2 final artifact 只能写入 models/final_consensus_v2")

    release = load_formal_release_metadata_without_external_reads(args.releases_root)
    data = policy["data_identity"]
    if (
        data["formal_release_id"] != release.release_id
        or data["dataset_manifest_sha256"] != release.manifest_sha256
    ):
        raise ValueError("formal release 与冻结 v2 policy 不一致")
    splits = load_train_validation_splits(release)
    rows = [*splits.train, *splits.validation]
    labels = np.asarray([int(row["normalized_label"]) for row in rows])
    if len(rows) != 921 or set(labels) != {0, 1}:
        raise ValueError("v2 final refit 必须为 921 个对齐二分类 development 样本")

    temporary_dir = prepare_output(args.output_dir)
    shutil.copy2(args.policy, temporary_dir / "v2_final_policy.json")
    try:
        member_records: list[dict[str, Any]] = []
        feature_records: dict[str, Any] = {}
        for spec in policy["members"]:
            matrix = featurize_smiles(
                (str(row["canonical_smiles"]) for row in rows), tuple(spec["feature_sets"])
            )
            estimator = build_estimator(
                ExperimentConfig(
                    model=spec["model"],
                    feature_sets=tuple(spec["feature_sets"]),
                    seed=int(policy["training"]["random_state"]),
                    tuning=False,
                    model_params=dict(spec["model_params"]),
                    threshold=float(policy["consensus_rule"]["threshold"]),
                ),
                binary_indices=matrix.binary_indices,
                descriptor_indices=matrix.descriptor_indices,
            ).fit(matrix.values, labels)
            model = estimator.named_steps["model"]
            preprocessing = estimator.named_steps["preprocess"]
            resolved_params = model.get_params(deep=False)
            if any(resolved_params.get(key) != value for key, value in spec["model_params"].items()):
                raise AssertionError(f"{spec['id']} 的训练参数与 policy 不一致")
            paths = member_artifact_paths(spec["id"])
            model_path = temporary_dir / paths["model"]
            preprocessing_path = temporary_dir / paths["preprocessing"]
            joblib.dump(model, model_path)
            joblib.dump(preprocessing, preprocessing_path)
            member_records.append(
                _member_record(
                    spec=spec,
                    model_path=model_path,
                    preprocessing_path=preprocessing_path,
                    matrix=matrix,
                    model_params=resolved_params,
                )
            )
            feature_records[spec["id"]] = feature_manifest(matrix)

        if [record["id"] for record in member_records] != list(MEMBER_IDS):
            raise AssertionError("实际训练成员顺序与冻结 policy 不一致")
        feature_sha = write_json_artifact(
            temporary_dir / "feature_manifest.json",
            {"feature_manifest_version": 1, "members": feature_records},
        )
        split_artifacts = {
            "train.csv": release.artifact_metadata("splits/primary_reproduction/train.csv"),
            "validation.csv": release.artifact_metadata(
                "splits/primary_reproduction/validation.csv"
            ),
        }
        training_manifest = build_training_manifest(
            policy_sha256=policy_sha256,
            release_id=release.release_id,
            dataset_manifest_sha256=release.manifest_sha256,
            split_artifacts=split_artifacts,
            labels=labels,
            members=member_records,
        )
        training_manifest["feature_manifest_sha256"] = feature_sha
        write_json_artifact(temporary_dir / "training_manifest.json", training_manifest)
        consensus_manifest = build_consensus_manifest(
            policy=policy, policy_sha256=policy_sha256, members=member_records
        )
        write_json_artifact(temporary_dir / "consensus_manifest.json", consensus_manifest)
        write_json_artifact(
            temporary_dir / "environment_manifest.json",
            {
                "environment_manifest_version": 1,
                "code_revision": code_revision(),
                "runtime_signature": runtime_signature(),
                "v2_final_policy_sha256": policy_sha256,
                "external_access": "denied",
            },
        )
        (temporary_dir / "training.log").write_text(
            "v2 final refit completed\nfit_split=train_validation\nexternal_access=denied\n"
            "prediction_artifact_written=false\n",
            encoding="utf-8",
        )
        hashes = build_artifact_hashes(temporary_dir)
        write_json_artifact(temporary_dir / "artifact_hashes.json", hashes)
        if {path.name for path in temporary_dir.iterdir()} != V2_FINAL_ARTIFACT_FILES:
            raise AssertionError("v2 final artifact 包含禁止或缺失文件")
        if args.output_dir.exists():
            args.output_dir.rmdir()
        os.replace(temporary_dir, args.output_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    print(json.dumps({"external_access": "denied", "output_dir": str(args.output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
