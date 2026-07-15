#!/usr/bin/env python3
"""生成冻结 v1 final model 的 train+validation SHAP 全局诊断，不读取 external。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import shap  # noqa: E402

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.featurizers import featurize_smiles  # noqa: E402
from modeling.split_loader import load_train_validation_splits  # noqa: E402
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-dir", type=Path, default=ROOT / "models" / "final_model_v1"
    )
    parser.add_argument(
        "--releases-root",
        type=Path,
        default=ROOT / "releases" / "dataset_assembly",
    )
    parser.add_argument(
        "--report", type=Path, default=ROOT / "reports" / "modeling" / "v1_descriptor_shap.md"
    )
    parser.add_argument(
        "--figure",
        type=Path,
        default=ROOT / "reports" / "figures" / "v1_descriptor_shap_global.png",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_canonical_json(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 不是 canonical JSON object")
    return value


def main() -> int:
    args = parse_args()
    artifact_dir = args.artifact_dir.resolve()
    expected_dir = (ROOT / "models" / "final_model_v1").resolve()
    if artifact_dir != expected_dir:
        raise PermissionError("SHAP 诊断只允许读取冻结的 models/final_model_v1 artifact")
    training = load_canonical_json(artifact_dir / "training_manifest.json")
    if training.get("external_access") != "denied" or training.get("fit_split") != "train_validation":
        raise PermissionError("不是批准的冻结 final artifact")
    release = load_formal_release_metadata_without_external_reads(args.releases_root)
    if (
        release.release_id != training.get("dataset_release_id")
        or release.manifest_sha256 != training.get("dataset_manifest_sha256")
    ):
        raise ValueError("当前 release 与冻结 final artifact 不一致")
    splits = load_train_validation_splits(release)
    rows = [*splits.train, *splits.validation]
    matrix = featurize_smiles(
        (str(row["canonical_smiles"]) for row in rows),
        ("rdkit_descriptors", "physicochemical"),
    )
    preprocessing = joblib.load(artifact_dir / "preprocessing.pkl")
    model = joblib.load(artifact_dir / "model.pkl")
    transformed = np.asarray(preprocessing.transform(matrix.values), dtype=float)
    retained = training["descriptor_preprocessing"]["retained_descriptor_columns"]
    if not isinstance(retained, list) or transformed.shape[1] != len(retained):
        raise ValueError("冻结预处理器输出与 retained descriptor manifest 不一致")
    if model.n_features_in_ != transformed.shape[1]:
        raise ValueError("冻结模型输入维度与预处理输出不一致")

    values = shap.TreeExplainer(model).shap_values(transformed)
    if isinstance(values, list):
        values = values[-1]
    shap_values = np.asarray(values, dtype=float)
    if shap_values.shape != transformed.shape:
        raise ValueError("SHAP 输出维度与模型输入不一致")
    mean_abs = np.mean(np.abs(shap_values), axis=0)
    mean_signed = np.mean(shap_values, axis=0)
    importance = np.asarray(model.feature_importances_, dtype=float)
    order = np.argsort(mean_abs)[::-1]
    top_count = min(20, len(retained))

    args.figure.parent.mkdir(parents=True, exist_ok=True)
    top = order[:top_count][::-1]
    figure, axis = plt.subplots(figsize=(9, 7))
    axis.barh(
        [str(retained[index]) for index in top],
        mean_abs[top],
        color="#2b6cb0",
    )
    axis.set_xlabel("mean |SHAP value| on frozen train+validation refit data")
    axis.set_title("v1 LightGBM descriptor global attribution")
    figure.tight_layout()
    figure.savefig(args.figure, dpi=180)
    plt.close(figure)

    report = [
        "# v1 descriptor SHAP diagnostic",
        "",
        "状态：`POST HOC, MODEL FROZEN`。",
        "",
        "本报告只读取冻结 v1 model、preprocessing artifact 与 formal release 的 train/validation CSV。它不读取 external split，也不会改变模型、特征、预处理或 threshold。SHAP 归因描述该模型在 refit 数据上的关联，不构成因果或机制结论。",
        "",
        "## Locked inputs",
        "",
        f"- final training manifest SHA-256: `{sha256(artifact_dir / 'training_manifest.json')}`",
        f"- dataset release: `{release.release_id}`",
        f"- dataset manifest SHA-256: `{release.manifest_sha256}`",
        f"- samples: `{len(rows)}` (train+validation)",
        f"- retained descriptors: `{len(retained)}`",
        f"- SHAP package: `{shap.__version__}`",
        f"- global attribution figure: `{args.figure.relative_to(ROOT)}`",
        "",
        "## Top global descriptor attributions",
        "",
        "| Rank | Descriptor | Mean \|SHAP\| | Mean SHAP | LightGBM split importance |",
        "|---:|---|---:|---:|---:|",
    ]
    for rank, index in enumerate(order[:top_count], start=1):
        report.append(
            f"| {rank} | {retained[index]} | {mean_abs[index]:.6f} | "
            f"{mean_signed[index]:.6f} | {int(importance[index])} |"
        )
    report.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "- Feature rankings are global attributions for the frozen train+validation refit data, not an external performance analysis.",
            "- Mean signed SHAP values aggregate directions across the refit data; feature-level dependence and individual-compound explanations require separate descriptive reports.",
            "- Any future uncertainty, applicability-domain, or consensus policy must be designed and evaluated on development data without using the locked v1 external result as feedback.",
            "",
        ]
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
