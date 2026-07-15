#!/usr/bin/env python3
"""报告冻结 v1 release 的 train 与 validation descriptor 分布差异，不读取 external。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.featurizers import featurize_smiles  # noqa: E402
from modeling.split_loader import load_train_validation_splits  # noqa: E402
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--releases-root",
        type=Path,
        default=ROOT / "releases" / "dataset_assembly",
    )
    parser.add_argument(
        "--training-manifest",
        type=Path,
        default=ROOT / "models" / "final_model_v1" / "training_manifest.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "reports" / "modeling" / "v1_train_validation_descriptor_shift.md",
    )
    return parser.parse_args()


def load_canonical_json(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 不是 canonical JSON object")
    return value


def main() -> int:
    args = parse_args()
    training = load_canonical_json(args.training_manifest)
    if training.get("external_access") != "denied":
        raise PermissionError("该诊断只能使用 external 仍锁定的 final training manifest")
    release = load_formal_release_metadata_without_external_reads(args.releases_root)
    if (
        release.release_id != training.get("dataset_release_id")
        or release.manifest_sha256 != training.get("dataset_manifest_sha256")
    ):
        raise ValueError("当前 release 与冻结 training manifest 不一致")
    splits = load_train_validation_splits(release)
    train = featurize_smiles(
        (str(row["canonical_smiles"]) for row in splits.train),
        ("rdkit_descriptors", "physicochemical"),
    )
    validation = featurize_smiles(
        (str(row["canonical_smiles"]) for row in splits.validation),
        ("rdkit_descriptors", "physicochemical"),
    )
    if train.feature_names != validation.feature_names:
        raise ValueError("train 与 validation descriptor 列不一致")
    x_train = np.asarray(train.values, dtype=float)
    x_validation = np.asarray(validation.values, dtype=float)
    train_mean = np.nanmean(x_train, axis=0)
    validation_mean = np.nanmean(x_validation, axis=0)
    train_std = np.nanstd(x_train, axis=0, ddof=0)
    validation_std = np.nanstd(x_validation, axis=0, ddof=0)
    pooled_std = np.sqrt((train_std**2 + validation_std**2) / 2)
    smd = np.divide(
        validation_mean - train_mean,
        pooled_std,
        out=np.zeros_like(train_mean),
        where=pooled_std > 1e-12,
    )
    train_missing = np.mean(np.isnan(x_train), axis=0)
    validation_missing = np.mean(np.isnan(x_validation), axis=0)
    order = np.argsort(np.abs(smd))[::-1]
    manifest_sha = hashlib.sha256(args.training_manifest.read_bytes()).hexdigest()
    lines = [
        "# v1 train-validation descriptor distribution diagnostic",
        "",
        "状态：`POST HOC, MODEL FROZEN`。",
        "",
        "本报告仅比较 formal release 中的 train 与 fixed validation descriptor 分布。它不读取 external，不改变已冻结模型、预处理或 threshold；标准化均值差（SMD）是描述性统计，不用于 v1 选择或调参。",
        "",
        "## Locked inputs",
        "",
        f"- final training manifest SHA-256: `{manifest_sha}`",
        f"- dataset release: `{release.release_id}`",
        f"- dataset manifest SHA-256: `{release.manifest_sha256}`",
        f"- train samples: `{len(splits.train)}`",
        f"- validation samples: `{len(splits.validation)}`",
        f"- descriptors compared: `{len(train.feature_names)}`",
        "",
        "## Largest absolute standardized mean differences",
        "",
        "| Rank | Descriptor | Train mean | Validation mean | SMD (validation - train) | Train missing | Validation missing |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for rank, index in enumerate(order[:20], start=1):
        lines.append(
            f"| {rank} | {train.feature_names[index]} | {train_mean[index]:.6f} | "
            f"{validation_mean[index]:.6f} | {smd[index]:.6f} | "
            f"{train_missing[index]:.4f} | {validation_missing[index]:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- This is not a train-vs-external shift report: primary external remains one-shot locked and its sample-level predictions were not retained.",
            "- Any v2 distributional or domain policy must be frozen before a separately authorized final evaluation.",
            "",
        ]
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
