#!/usr/bin/env python3
"""用 ECFP4 最大 train similarity 分层诊断 fixed validation，不读取 external。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
from scipy import sparse  # noqa: E402

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.experiment_config import ExperimentConfig  # noqa: E402
from modeling.featurizers import featurize_smiles  # noqa: E402
from modeling.metrics import binary_confusion_counts, binary_metrics  # noqa: E402
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
        default=ROOT / "reports" / "modeling" / "v2_validation_applicability_domain.md",
    )
    return parser.parse_args()


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 不是 canonical JSON object")
    return value


def maximum_tanimoto(train: sparse.csr_matrix, query: sparse.csr_matrix) -> np.ndarray:
    """在固定的 ECFP4 bit matrix 上计算每个 query 到 train 的最大 Tanimoto。"""

    intersections = query @ train.T
    query_bits = np.asarray(query.sum(axis=1)).ravel()
    train_bits = np.asarray(train.sum(axis=1)).ravel()
    result = np.zeros(query.shape[0], dtype=float)
    for index in range(query.shape[0]):
        row = intersections.getrow(index)
        denominators = query_bits[index] + train_bits[row.indices] - row.data
        values = np.divide(
            row.data,
            denominators,
            out=np.zeros_like(row.data, dtype=float),
            where=denominators > 0,
        )
        result[index] = float(values.max()) if len(values) else 0.0
    return result


def main() -> int:
    args = parse_args()
    config = load_canonical_json(args.config)
    if config.get("external_access") != "denied" or config.get("threshold") != 0.5:
        raise PermissionError("适用域诊断只接受冻结 development-only config")
    descriptor_spec = next(
        item for item in config["models"] if item["id"] == "lightgbm_descriptors"
    )
    release = load_formal_release_metadata_without_external_reads(args.releases_root)
    splits = load_train_validation_splits(release)
    y_train = np.asarray([int(row["normalized_label"]) for row in splits.train])
    y_validation = np.asarray([int(row["normalized_label"]) for row in splits.validation])
    descriptor_train = featurize_smiles(
        (str(row["canonical_smiles"]) for row in splits.train),
        tuple(descriptor_spec["feature_sets"]),
    )
    descriptor_validation = featurize_smiles(
        (str(row["canonical_smiles"]) for row in splits.validation),
        tuple(descriptor_spec["feature_sets"]),
    )
    model = build_estimator(
        ExperimentConfig(
            model="lightgbm",
            feature_sets=tuple(descriptor_spec["feature_sets"]),
            seed=int(config["random_state"]),
            tuning=False,
            model_params=dict(descriptor_spec["model_params"]),
            threshold=0.5,
        ),
        binary_indices=descriptor_train.binary_indices,
        descriptor_indices=descriptor_train.descriptor_indices,
    ).fit(descriptor_train.values, y_train)
    probability = predict_probability(model, descriptor_validation.values)
    ecfp_train = featurize_smiles(
        (str(row["canonical_smiles"]) for row in splits.train), ("ecfp4",)
    ).values
    ecfp_validation = featurize_smiles(
        (str(row["canonical_smiles"]) for row in splits.validation), ("ecfp4",)
    ).values
    if not sparse.isspmatrix_csr(ecfp_train) or not sparse.isspmatrix_csr(ecfp_validation):
        raise ValueError("ECFP4 applicability-domain 输入必须是 CSR matrix")
    similarity = maximum_tanimoto(ecfp_train, ecfp_validation)
    bins = (
        ("0.85+", similarity >= 0.85),
        ("0.70-0.85", (similarity >= 0.70) & (similarity < 0.85)),
        ("0.50-0.70", (similarity >= 0.50) & (similarity < 0.70)),
        ("<0.50", similarity < 0.50),
    )
    lines = [
        "# v2 validation applicability-domain diagnostic",
        "",
        "状态：`POST HOC, DEVELOPMENT ONLY`。",
        "",
        "每个 fixed-validation 化合物按其到 train 的最大 ECFP4 Tanimoto similarity 分桶。性能来自冻结的 LightGBM + descriptors train-fit model；该报告不读取 external，也不定义或修改任何 final-evaluation policy。",
        "",
        "## Locked inputs",
        "",
        f"- dataset release: `{release.release_id}`",
        f"- dataset manifest SHA-256: `{release.manifest_sha256}`",
        f"- train / validation: `{len(splits.train)} / {len(splits.validation)}`",
        "- model: `lightgbm_descriptors` from `consensus_v2_development_v1.json`",
        f"- threshold: `{config['threshold']}`",
        "",
        "## Similarity-stratified validation result",
        "",
        "| Max ECFP4 Tanimoto bin | Samples | Mean similarity | AUROC | MCC | Accuracy | TN / FP / FN / TP |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name, mask in bins:
        truth = y_validation[mask]
        probabilities = probability[mask]
        if not len(truth):
            lines.append(f"| {name} | 0 | null | null | null | null | null |")
            continue
        metrics = binary_metrics(truth, probabilities, threshold=0.5)
        confusion = binary_confusion_counts(truth, probabilities, threshold=0.5)
        auroc = "null" if metrics["auroc"] is None else f"{metrics['auroc']:.6f}"
        lines.append(
            f"| {name} | {len(truth)} | {similarity[mask].mean():.6f} | {auroc} | "
            f"{metrics['mcc']:.6f} | {metrics['accuracy']:.6f} | "
            f"{confusion['true_negative']} / {confusion['false_positive']} / "
            f"{confusion['false_negative']} / {confusion['true_positive']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "- These bins are descriptive development diagnostics, not a calibrated applicability-domain threshold or a v1 external analysis.",
            "- A v2 domain policy must be fixed before a separately authorized final evaluation; this result cannot be used to reopen v1.",
            "",
        ]
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
