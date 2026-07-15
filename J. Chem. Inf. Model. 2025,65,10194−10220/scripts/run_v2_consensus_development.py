#!/usr/bin/env python3
"""运行冻结的 v2 consensus 开发实验；只读取 train/validation。"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import lightgbm  # noqa: E402
import numpy as np  # noqa: E402
import rdkit  # noqa: E402
import sklearn  # noqa: E402

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.experiment_config import ExperimentConfig  # noqa: E402
from modeling.experiment_manifest import write_json_artifact  # noqa: E402
from modeling.featurizers import featurize_smiles  # noqa: E402
from modeling.metrics import binary_confusion_counts, binary_metrics  # noqa: E402
from modeling.sanity_checks import class_counts  # noqa: E402
from modeling.split_loader import load_train_validation_splits  # noqa: E402
from modeling.train_baseline import build_estimator, predict_probability  # noqa: E402
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


EXPECTED_CONFIG_KEYS = {
    "consensus_rule",
    "external_access",
    "final_evaluation",
    "models",
    "random_state",
    "selection_policy",
    "status",
    "threshold",
    "training_protocol",
    "version",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs" / "consensus_v2_development_v1.json"
    )
    parser.add_argument(
        "--releases-root",
        type=Path,
        default=ROOT / "releases" / "dataset_assembly",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports" / "modeling" / "v2_consensus_development_v1",
    )
    return parser.parse_args()


def load_config(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    config = json.loads(raw.decode("utf-8"))
    if not isinstance(config, dict) or raw != canonical_json_bytes(config):
        raise ValueError("consensus config 必须是 canonical JSON object")
    if set(config) != EXPECTED_CONFIG_KEYS:
        raise ValueError("consensus config 字段集合不正确")
    if (
        config["version"] != 1
        or config["status"] != "FROZEN_DEVELOPMENT_ONLY"
        or config["external_access"] != "denied"
        or config["threshold"] != 0.5
        or config["training_protocol"] != "fit_train_once_evaluate_fixed_validation_once"
    ):
        raise ValueError("consensus config 未遵循冻结 development-only 约束")
    models = config["models"]
    if not isinstance(models, list) or [item.get("id") for item in models] != [
        "lightgbm_descriptors",
        "random_forest_maccs",
        "random_forest_ecfp4",
    ]:
        raise ValueError("consensus config 模型顺序或 ID 不正确")
    return config, hashlib.sha256(raw).hexdigest()


def runtime_signature() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scikit_learn": sklearn.__version__,
        "lightgbm": lightgbm.__version__,
        "rdkit": rdkit.__version__,
    }


def _prepare_output(output_dir: Path) -> Path:
    if output_dir.exists():
        raise FileExistsError(f"development consensus output 已存在，拒绝覆盖：{output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=".v2_consensus.", dir=output_dir.parent))


def main() -> int:
    args = parse_args()
    config, config_sha256 = load_config(args.config)
    release = load_formal_release_metadata_without_external_reads(args.releases_root)
    splits = load_train_validation_splits(release)
    y_train = np.asarray([int(row["normalized_label"]) for row in splits.train])
    y_validation = np.asarray([int(row["normalized_label"]) for row in splits.validation])
    probabilities: list[np.ndarray] = []
    individual: dict[str, Any] = {}
    for model_spec in config["models"]:
        feature_sets = tuple(str(item) for item in model_spec["feature_sets"])
        x_train = featurize_smiles(
            (str(row["canonical_smiles"]) for row in splits.train), feature_sets
        )
        x_validation = featurize_smiles(
            (str(row["canonical_smiles"]) for row in splits.validation), feature_sets
        )
        estimator_config = ExperimentConfig(
            model=str(model_spec["model"]),
            feature_sets=feature_sets,
            seed=int(config["random_state"]),
            tuning=False,
            model_params=dict(model_spec["model_params"]),
            threshold=float(config["threshold"]),
        )
        estimator = build_estimator(
            estimator_config,
            binary_indices=x_train.binary_indices,
            descriptor_indices=x_train.descriptor_indices,
        ).fit(x_train.values, y_train)
        probability = predict_probability(estimator, x_validation.values)
        probabilities.append(probability)
        individual[str(model_spec["id"])] = {
            "feature_count": len(x_train.feature_names),
            "validation_metrics": binary_metrics(y_validation, probability, threshold=0.5),
            "validation_confusion": binary_confusion_counts(y_validation, probability, threshold=0.5),
        }
    probability_matrix = np.column_stack(probabilities)
    positive = np.all(probability_matrix >= 0.5, axis=1)
    negative = np.all(probability_matrix < 0.5, axis=1)
    covered = positive | negative
    labels = np.full(len(y_validation), "inconclusive", dtype=object)
    labels[positive] = "positive"
    labels[negative] = "negative"
    covered_predictions = positive[covered].astype(int)
    covered_truth = y_validation[covered]
    if not len(covered_truth):
        raise ValueError("冻结 consensus rule 未覆盖任何 validation 样本")
    coverage = float(np.mean(covered))
    covered_probability = covered_predictions.astype(float)
    consensus = {
        "coverage": coverage,
        "covered_count": int(np.count_nonzero(covered)),
        "inconclusive_count": int(np.count_nonzero(~covered)),
        "inconclusive_rate": float(np.mean(~covered)),
        "covered_metrics": binary_metrics(covered_truth, covered_probability, threshold=0.5),
        "covered_confusion": binary_confusion_counts(
            covered_truth, covered_probability, threshold=0.5
        ),
        "covered_correct_count": int(np.count_nonzero(covered_truth == covered_predictions)),
        "covered_incorrect_count": int(np.count_nonzero(covered_truth != covered_predictions)),
        "positive_call_count": int(np.count_nonzero(labels == "positive")),
        "negative_call_count": int(np.count_nonzero(labels == "negative")),
    }
    temporary_dir = _prepare_output(args.output_dir)
    try:
        manifest = {
            "consensus_development_manifest_version": 1,
            "config_sha256": config_sha256,
            "dataset_release_id": release.release_id,
            "dataset_manifest_sha256": release.manifest_sha256,
            "split_artifacts": {
                "train.csv": release.artifact_metadata("splits/primary_reproduction/train.csv"),
                "validation.csv": release.artifact_metadata(
                    "splits/primary_reproduction/validation.csv"
                ),
            },
            "data_summary": {
                "train": {"sample_count": len(y_train), "class_counts": class_counts(y_train)},
                "validation": {
                    "sample_count": len(y_validation),
                    "class_counts": class_counts(y_validation),
                },
            },
            "configuration": config,
            "individual_validation_results": individual,
            "consensus_validation_result": consensus,
            "prediction_artifact_written": False,
            "runtime_signature": runtime_signature(),
            "external_access": "denied",
        }
        write_json_artifact(temporary_dir / "consensus_development_manifest.json", manifest)
        lines = [
            "# v2 development-only consensus experiment",
            "",
            "状态：`COMPLETE — DEVELOPMENT ONLY`。",
            "",
            "本报告固定三模型与 unanimity/inconclusive 规则后，只在 train fit 和 fixed validation 评估一次。它没有读取 external，也没有写出样本级预测。",
            "",
            "## Consensus result on fixed validation",
            "",
            f"- coverage: `{consensus['coverage']:.6f}` ({consensus['covered_count']} / {len(y_validation)})",
            f"- inconclusive: `{consensus['inconclusive_rate']:.6f}` ({consensus['inconclusive_count']} / {len(y_validation)})",
            f"- covered-set MCC: `{consensus['covered_metrics']['mcc']:.6f}`",
            f"- covered-set accuracy: `{consensus['covered_metrics']['accuracy']:.6f}`",
            f"- covered confusion (TN / FP / FN / TP): `{consensus['covered_confusion']['true_negative']} / {consensus['covered_confusion']['false_positive']} / {consensus['covered_confusion']['false_negative']} / {consensus['covered_confusion']['true_positive']}`",
            "",
            "## Individual fixed-validation results",
            "",
            "| Model | Features | AUROC | AUPRC | MCC |",
            "|---|---:|---:|---:|---:|",
        ]
        for model_id, value in individual.items():
            metrics = value["validation_metrics"]
            lines.append(
                f"| {model_id} | {value['feature_count']} | {metrics['auroc']:.6f} | "
                f"{metrics['auprc']:.6f} | {metrics['mcc']:.6f} |"
            )
        lines.extend(
            [
                "",
                "该 development result 不能用于修改已封存的 v1，也不授权任何 external evaluation。任何 v2 final evaluation 需要新的、单独冻结的 final artifact 和评估协议。",
                "",
            ]
        )
        (temporary_dir / "consensus_development.md").write_text("\n".join(lines), encoding="utf-8")
        temporary_dir.replace(args.output_dir)
    except Exception:
        import shutil

        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    print(json.dumps({"output_dir": str(args.output_dir), "external_access": "denied"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
