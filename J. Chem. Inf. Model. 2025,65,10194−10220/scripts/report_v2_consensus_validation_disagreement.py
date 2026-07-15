#!/usr/bin/env python3
"""汇总冻结 v2 candidates 在 validation 上的分歧和错误互补性，不读取 external。"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.experiment_config import ExperimentConfig  # noqa: E402
from modeling.featurizers import featurize_smiles  # noqa: E402
from modeling.split_loader import load_train_validation_splits  # noqa: E402
from modeling.train_baseline import build_estimator, predict_probability  # noqa: E402
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


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
        "--report",
        type=Path,
        default=ROOT / "reports" / "modeling" / "v2_consensus_validation_disagreement.md",
    )
    return parser.parse_args()


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 不是 canonical JSON object")
    return value


def main() -> int:
    args = parse_args()
    config = load_canonical_json(args.config)
    if config.get("external_access") != "denied" or config.get("threshold") != 0.5:
        raise PermissionError("只能诊断 external 被拒绝且 threshold 冻结的 v2 config")
    release = load_formal_release_metadata_without_external_reads(args.releases_root)
    splits = load_train_validation_splits(release)
    y_train = np.asarray([int(row["normalized_label"]) for row in splits.train])
    y_validation = np.asarray([int(row["normalized_label"]) for row in splits.validation])
    predictions: dict[str, np.ndarray] = {}
    for spec in config["models"]:
        feature_sets = tuple(str(item) for item in spec["feature_sets"])
        x_train = featurize_smiles(
            (str(row["canonical_smiles"]) for row in splits.train), feature_sets
        )
        x_validation = featurize_smiles(
            (str(row["canonical_smiles"]) for row in splits.validation), feature_sets
        )
        estimator = build_estimator(
            ExperimentConfig(
                model=str(spec["model"]),
                feature_sets=feature_sets,
                seed=int(config["random_state"]),
                tuning=False,
                model_params=dict(spec["model_params"]),
                threshold=0.5,
            ),
            binary_indices=x_train.binary_indices,
            descriptor_indices=x_train.descriptor_indices,
        ).fit(x_train.values, y_train)
        predictions[str(spec["id"])] = (
            predict_probability(estimator, x_validation.values) >= 0.5
        ).astype(int)
    pairs: list[dict[str, Any]] = []
    for first, second in combinations(predictions, 2):
        first_prediction = predictions[first]
        second_prediction = predictions[second]
        first_error = first_prediction != y_validation
        second_error = second_prediction != y_validation
        union = np.count_nonzero(first_error | second_error)
        pairs.append(
            {
                "pair": f"{first} / {second}",
                "class_agreement": int(np.count_nonzero(first_prediction == second_prediction)),
                "both_correct": int(np.count_nonzero(~first_error & ~second_error)),
                "only_first_wrong": int(np.count_nonzero(first_error & ~second_error)),
                "only_second_wrong": int(np.count_nonzero(~first_error & second_error)),
                "both_wrong": int(np.count_nonzero(first_error & second_error)),
                "error_jaccard": float(np.count_nonzero(first_error & second_error) / union)
                if union
                else 0.0,
            }
        )
    matrix = np.column_stack([predictions[key] for key in predictions])
    all_agree = np.all(matrix == matrix[:, [0]], axis=1)
    covered_prediction = matrix[:, 0]
    covered_correct = all_agree & (covered_prediction == y_validation)
    covered_wrong = all_agree & (covered_prediction != y_validation)
    lines = [
        "# v2 validation disagreement and error-complementarity diagnostic",
        "",
        "状态：`POST HOC, DEVELOPMENT ONLY`。",
        "",
        "本报告按冻结的 v2 config 重现 train fit / fixed validation predictions，并仅输出聚合的模型分歧与错误重叠统计。它不保存样本级 prediction，不读取 external，且不改变 candidate、parameter、threshold 或 consensus rule。",
        "",
        "## Locked inputs",
        "",
        f"- dataset release: `{release.release_id}`",
        f"- dataset manifest SHA-256: `{release.manifest_sha256}`",
        f"- validation samples: `{len(y_validation)}`",
        f"- threshold: `{config['threshold']}`",
        "",
        "## Pairwise agreement and error overlap",
        "",
        "| Pair | Class agreement | Both correct | Only first wrong | Only second wrong | Both wrong | Error Jaccard |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in pairs:
        lines.append(
            f"| {row['pair']} | {row['class_agreement']} | {row['both_correct']} | "
            f"{row['only_first_wrong']} | {row['only_second_wrong']} | {row['both_wrong']} | "
            f"{row['error_jaccard']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Unanimity rule summary",
            "",
            f"- unanimous calls: `{int(np.count_nonzero(all_agree))}`",
            f"- unanimous correct: `{int(np.count_nonzero(covered_correct))}`",
            f"- unanimous wrong: `{int(np.count_nonzero(covered_wrong))}`",
            f"- inconclusive due to disagreement: `{int(np.count_nonzero(~all_agree))}`",
            "",
            "A nonzero count in either ‘only ... wrong’ column is evidence that the two fixed models do not make identical validation errors. This is descriptive evidence for the predeclared consensus research question, not permission to select a different rule after seeing validation.",
            "",
        ]
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
