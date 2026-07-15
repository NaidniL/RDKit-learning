#!/usr/bin/env python3
"""一次性生成冻结 v1 的 post-hoc primary-external 诊断；不允许模型反馈。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
from rdkit import Chem  # noqa: E402
from rdkit.Chem.Scaffolds import MurckoScaffold  # noqa: E402
from scipy import sparse  # noqa: E402

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.evaluation_guard import assert_split_access  # noqa: E402
from modeling.experiment_manifest import sha256_file, write_json_artifact  # noqa: E402
from modeling.featurizers import featurize_smiles  # noqa: E402
from modeling.metrics import binary_confusion_counts, binary_metrics  # noqa: E402
from modeling.train_baseline import predict_probability  # noqa: E402
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


TRAIN_PATH = "splits/primary_reproduction/train.csv"
EXTERNAL_PATH = "splits/external_test.csv"
OUTPUT_FILES = {
    "diagnostic_manifest.json",
    "external_error_analysis.md",
    "similarity_scaffold_stratified_metrics.md",
    "domain_aware_performance.md",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--authorization",
        type=Path,
        default=ROOT / "configs" / "v1_posthoc_external_diagnostic_authorization_v1.json",
    )
    parser.add_argument(
        "--training-manifest",
        type=Path,
        default=ROOT / "models" / "final_model_v1" / "training_manifest.json",
    )
    parser.add_argument(
        "--external-evaluation-manifest",
        type=Path,
        default=ROOT
        / "reports"
        / "modeling"
        / "final_external_evaluation_v1"
        / "external_evaluation_manifest.json",
    )
    parser.add_argument(
        "--releases-root",
        type=Path,
        default=ROOT / "releases" / "dataset_assembly",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports" / "modeling" / "v1_posthoc_external_diagnostics",
    )
    return parser.parse_args()


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 不是 canonical JSON object")
    return value


def maximum_tanimoto(train: sparse.csr_matrix, query: sparse.csr_matrix) -> np.ndarray:
    intersections = query @ train.T
    query_bits = np.asarray(query.sum(axis=1)).ravel()
    train_bits = np.asarray(train.sum(axis=1)).ravel()
    output = np.zeros(query.shape[0], dtype=float)
    for index in range(query.shape[0]):
        row = intersections.getrow(index)
        denominator = query_bits[index] + train_bits[row.indices] - row.data
        values = np.divide(
            row.data,
            denominator,
            out=np.zeros_like(row.data, dtype=float),
            where=denominator > 0,
        )
        output[index] = float(values.max()) if len(values) else 0.0
    return output


def scaffold(smiles: str) -> str:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError("canonical_smiles 无法解析")
    return str(MurckoScaffold.MurckoScaffoldSmiles(mol=molecule))


def metrics_row(
    truth: np.ndarray, probability: np.ndarray, *, threshold: float = 0.5
) -> dict[str, Any]:
    if not len(truth):
        return {"sample_count": 0, "metrics": None, "confusion": None}
    return {
        "sample_count": int(len(truth)),
        "metrics": binary_metrics(truth, probability, threshold=threshold),
        "confusion": binary_confusion_counts(truth, probability, threshold=threshold),
    }


def descriptor_profile(
    values: np.ndarray, names: tuple[str, ...], left: np.ndarray, right: np.ndarray
) -> list[dict[str, Any]]:
    """返回两类错误/正确组的最大绝对 SMD，不保留样本级特征。"""

    if not len(left) or not len(right):
        return []
    left_values = values[left]
    right_values = values[right]
    left_mean = np.nanmean(left_values, axis=0)
    right_mean = np.nanmean(right_values, axis=0)
    pooled = np.sqrt((np.nanvar(left_values, axis=0) + np.nanvar(right_values, axis=0)) / 2)
    smd = np.divide(
        left_mean - right_mean,
        pooled,
        out=np.zeros_like(left_mean),
        where=pooled > 1e-12,
    )
    order = np.argsort(np.abs(smd))[::-1][:10]
    return [
        {
            "descriptor": names[index],
            "left_mean": float(left_mean[index]),
            "right_mean": float(right_mean[index]),
            "smd": float(smd[index]),
        }
        for index in order
    ]


def markdown_metrics(row: dict[str, Any]) -> tuple[str, str, str]:
    if row["metrics"] is None or row["confusion"] is None:
        return "null", "null", "null"
    metrics = row["metrics"]
    confusion = row["confusion"]
    auroc = "null" if metrics["auroc"] is None else f"{metrics['auroc']:.6f}"
    return (
        auroc,
        f"{metrics['mcc']:.6f}",
        f"{confusion['true_negative']} / {confusion['false_positive']} / "
        f"{confusion['false_negative']} / {confusion['true_positive']}",
    )


def main() -> int:
    args = parse_args()
    authorization = load_canonical_json(args.authorization)
    training = load_canonical_json(args.training_manifest)
    evaluation = load_canonical_json(args.external_evaluation_manifest)
    required_authorization = {
        "allowed_outputs",
        "analysis_scope",
        "external_split",
        "final_evaluation_manifest_sha256",
        "final_training_manifest_sha256",
        "model_change_prohibited",
        "prediction_csv_prohibited",
        "repeat_diagnostic_prohibited",
        "status",
        "threshold",
        "version",
    }
    if set(authorization) != required_authorization:
        raise ValueError("post-hoc authorization 字段集合不正确")
    if (
        authorization["status"]
        != "FROZEN_POST_HOC_EXTERNAL_DIAGNOSTIC_AUTHORIZED"
        or authorization["analysis_scope"] != "post_hoc_descriptive_only"
        or authorization["external_split"] != EXTERNAL_PATH
        or authorization["threshold"] != 0.5
        or authorization["model_change_prohibited"] is not True
        or authorization["prediction_csv_prohibited"] is not True
        or authorization["repeat_diagnostic_prohibited"] is not True
    ):
        raise PermissionError("post-hoc authorization 未满足冻结诊断约束")
    if authorization["final_training_manifest_sha256"] != sha256_file(args.training_manifest):
        raise ValueError("authorization 与 final training manifest 不一致")
    if authorization["final_evaluation_manifest_sha256"] != sha256_file(
        args.external_evaluation_manifest
    ):
        raise ValueError("authorization 与 final evaluation manifest 不一致")
    if args.output_dir.exists():
        raise FileExistsError(f"post-hoc external diagnostic 已完成，拒绝重复读取：{args.output_dir}")
    if training["threshold"] != evaluation["threshold"] != authorization["threshold"]:
        raise ValueError("冻结阈值不一致")
    if training["model_artifact"] != evaluation["model_artifact"]:
        raise ValueError("evaluation model artifact 与 training manifest 不一致")
    if training["preprocessing_artifact"] != evaluation["preprocessing_artifact"]:
        raise ValueError("evaluation preprocessing artifact 与 training manifest 不一致")

    # The current user-authorized post-hoc scope is explicit and one-shot; it still
    # requires the standard external access guard before opening the split.
    assert_split_access(EXTERNAL_PATH, stage="external_final")
    release = load_formal_release_metadata_without_external_reads(args.releases_root)
    if (
        release.release_id != training["dataset_release_id"]
        or release.manifest_sha256 != training["dataset_manifest_sha256"]
        or release.manifest_sha256 != evaluation["dataset_manifest_sha256"]
    ):
        raise ValueError("当前 release 与冻结 v1 artifact 不一致")
    train_rows = release.read_csv(TRAIN_PATH)
    external_rows = release.read_csv(EXTERNAL_PATH)
    if release.artifact_metadata(EXTERNAL_PATH) != {
        key: value for key, value in evaluation["external_split"].items() if key != "path"
    }:
        raise ValueError("external split artifact 与 final evaluation 不一致")
    y_external = np.asarray([int(row["normalized_label"]) for row in external_rows])
    descriptor_external = featurize_smiles(
        (str(row["canonical_smiles"]) for row in external_rows),
        ("rdkit_descriptors", "physicochemical"),
    )
    if list(descriptor_external.feature_names) != training["descriptor_list"]:
        raise ValueError("external descriptor layout 与冻结 model 不一致")
    model_dir = args.training_manifest.parent
    model = joblib.load(model_dir / "model.pkl")
    preprocessing = joblib.load(model_dir / "preprocessing.pkl")
    probability = predict_probability(
        model, preprocessing.transform(descriptor_external.values)
    )
    predicted = (probability >= 0.5).astype(int)
    expected_confusion = evaluation["external_confusion"]
    actual_confusion = binary_confusion_counts(y_external, probability, threshold=0.5)
    if actual_confusion != expected_confusion:
        raise ValueError("post-hoc prediction 未复现冻结 external confusion counts")
    prediction_digest = hashlib.sha256(
        canonical_json_bytes(
            [
                {
                    "compound_id": str(row["compound_id"]),
                    "normalized_label": int(label),
                    "probability": float(value),
                }
                for row, label, value in zip(external_rows, y_external, probability, strict=True)
            ]
        )
    ).hexdigest()
    if prediction_digest != evaluation["external_prediction_digest"]["sha256"]:
        raise ValueError("post-hoc prediction digest 未复现冻结 external digest")

    ecfp_train = featurize_smiles(
        (str(row["canonical_smiles"]) for row in train_rows), ("ecfp4",)
    ).values
    ecfp_external = featurize_smiles(
        (str(row["canonical_smiles"]) for row in external_rows), ("ecfp4",)
    ).values
    if not sparse.isspmatrix_csr(ecfp_train) or not sparse.isspmatrix_csr(ecfp_external):
        raise ValueError("ECFP4 similarity 输入必须为 CSR matrix")
    similarity = maximum_tanimoto(ecfp_train, ecfp_external)
    train_scaffolds = {scaffold(str(row["canonical_smiles"])) for row in train_rows}
    external_scaffolds = np.asarray(
        [scaffold(str(row["canonical_smiles"])) for row in external_rows], dtype=object
    )
    scaffold_seen = np.asarray(
        [value != "" and value in train_scaffolds for value in external_scaffolds], dtype=bool
    )

    error_groups = {
        "false_positive_vs_true_negative": (predicted == 1) & (y_external == 0),
        "true_negative": (predicted == 0) & (y_external == 0),
        "false_negative_vs_true_positive": (predicted == 0) & (y_external == 1),
        "true_positive": (predicted == 1) & (y_external == 1),
    }
    error_profiles = {
        "false_positive_vs_true_negative": descriptor_profile(
            np.asarray(descriptor_external.values, dtype=float),
            descriptor_external.feature_names,
            error_groups["false_positive_vs_true_negative"],
            error_groups["true_negative"],
        ),
        "false_negative_vs_true_positive": descriptor_profile(
            np.asarray(descriptor_external.values, dtype=float),
            descriptor_external.feature_names,
            error_groups["false_negative_vs_true_positive"],
            error_groups["true_positive"],
        ),
    }
    similarity_bins = (
        ("0.85+", similarity >= 0.85),
        ("0.70-0.85", (similarity >= 0.70) & (similarity < 0.85)),
        ("0.50-0.70", (similarity >= 0.50) & (similarity < 0.70)),
        ("<0.50", similarity < 0.50),
    )
    similarity_results = {
        name: {
            **metrics_row(y_external[mask], probability[mask]),
            "mean_similarity": float(similarity[mask].mean()) if np.any(mask) else None,
        }
        for name, mask in similarity_bins
    }
    scaffold_results = {
        "scaffold_seen": metrics_row(y_external[scaffold_seen], probability[scaffold_seen]),
        "scaffold_novel_or_empty": metrics_row(
            y_external[~scaffold_seen], probability[~scaffold_seen]
        ),
    }
    domain_masks = {
        "in_domain": (similarity >= 0.70) & scaffold_seen,
        "near_domain": (similarity >= 0.50) & ~((similarity >= 0.70) & scaffold_seen),
        "out_of_domain": similarity < 0.50,
    }
    domain_results = {
        name: {
            **metrics_row(y_external[mask], probability[mask]),
            "mean_similarity": float(similarity[mask].mean()) if np.any(mask) else None,
            "scaffold_seen_count": int(np.count_nonzero(scaffold_seen[mask])),
        }
        for name, mask in domain_masks.items()
    }

    temporary_dir = Path(tempfile.mkdtemp(prefix=".v1_posthoc_external.", dir=args.output_dir.parent))
    try:
        manifest = {
            "posthoc_diagnostic_manifest_version": 1,
            "authorization_sha256": sha256_file(args.authorization),
            "final_training_manifest_sha256": sha256_file(args.training_manifest),
            "final_evaluation_manifest_sha256": sha256_file(args.external_evaluation_manifest),
            "dataset_release_id": release.release_id,
            "dataset_manifest_sha256": release.manifest_sha256,
            "external_split": {"path": EXTERNAL_PATH, **release.artifact_metadata(EXTERNAL_PATH)},
            "model_artifact": training["model_artifact"],
            "preprocessing_artifact": training["preprocessing_artifact"],
            "feature_manifest_sha256": training["feature_manifest_sha256"],
            "threshold": 0.5,
            "reproduced_external_metrics": binary_metrics(y_external, probability, threshold=0.5),
            "reproduced_external_confusion": actual_confusion,
            "prediction_digest": {"sha256": prediction_digest, "rows": len(y_external), "artifact_written": False},
            "error_counts": {
                "true_negative": int(np.count_nonzero((predicted == 0) & (y_external == 0))),
                "false_positive": int(np.count_nonzero((predicted == 1) & (y_external == 0))),
                "false_negative": int(np.count_nonzero((predicted == 0) & (y_external == 1))),
                "true_positive": int(np.count_nonzero((predicted == 1) & (y_external == 1))),
            },
            "similarity_results": similarity_results,
            "scaffold_results": scaffold_results,
            "domain_results": domain_results,
            "error_descriptor_profiles": error_profiles,
            "model_change_prohibited": True,
            "prediction_csv_prohibited": True,
            "external_access": "post_hoc_diagnostic_once",
        }
        write_json_artifact(temporary_dir / "diagnostic_manifest.json", manifest)
        error_lines = [
            "# v1 post-hoc primary external error analysis",
            "",
            "状态：`COMPLETE — DESCRIPTIVE ONLY`。",
            "",
            "本报告在显式 post-hoc 授权下复现冻结 v1 的 primary external predictions。它没有改变模型、特征、预处理、阈值或选择规则，也没有写出样本级 prediction 文件。",
            "",
            "## Reproduced aggregate errors",
            "",
            f"- TN / FP / FN / TP: `{actual_confusion['true_negative']} / {actual_confusion['false_positive']} / {actual_confusion['false_negative']} / {actual_confusion['true_positive']}`",
            f"- prediction digest reproduced: `{prediction_digest}`",
            "",
        ]
        for title, profile in error_profiles.items():
            error_lines.extend(
                [
                    f"## {title.replace('_', ' ')} descriptor profile",
                    "",
                    "| Descriptor | Left mean | Right mean | SMD |",
                    "|---|---:|---:|---:|",
                ]
            )
            error_lines.extend(
                f"| {row['descriptor']} | {row['left_mean']:.6f} | {row['right_mean']:.6f} | {row['smd']:.6f} |"
                for row in profile
            )
            error_lines.append("")
        error_lines.extend(
            [
                "这些差异是描述性 error-profile 信号，不构成因果解释或 v1 修改依据。",
                "",
            ]
        )
        (temporary_dir / "external_error_analysis.md").write_text("\n".join(error_lines), encoding="utf-8")
        stratified_lines = [
            "# v1 primary external similarity and scaffold stratified metrics",
            "",
            "状态：`COMPLETE — DESCRIPTIVE ONLY`。",
            "",
            "## Maximum ECFP4 Tanimoto similarity to train",
            "",
            "| Bin | Samples | Mean similarity | AUROC | MCC | TN / FP / FN / TP |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for name, row in similarity_results.items():
            auroc, mcc, confusion = markdown_metrics(row)
            mean_similarity = "null" if row["mean_similarity"] is None else f"{row['mean_similarity']:.6f}"
            stratified_lines.append(
                f"| {name} | {row['sample_count']} | {mean_similarity} | {auroc} | {mcc} | {confusion} |"
            )
        stratified_lines.extend(
            [
                "",
                "## Murcko scaffold support relative to train",
                "",
                "| Status | Samples | AUROC | MCC | TN / FP / FN / TP |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for name, row in scaffold_results.items():
            auroc, mcc, confusion = markdown_metrics(row)
            stratified_lines.append(
                f"| {name} | {row['sample_count']} | {auroc} | {mcc} | {confusion} |"
            )
        stratified_lines.append("")
        (temporary_dir / "similarity_scaffold_stratified_metrics.md").write_text(
            "\n".join(stratified_lines), encoding="utf-8"
        )
        domain_lines = [
            "# v1 post-hoc domain-aware performance",
            "",
            "状态：`COMPLETE — DESCRIPTIVE ONLY`。",
            "",
            "固定的 post-hoc domain categories：in-domain = maximum ECFP4 similarity >= 0.70 且 Murcko scaffold 在 train 中出现；near-domain = similarity >= 0.50 但不满足 in-domain；out-of-domain = similarity < 0.50。类别仅用于描述已冻结结果，不改变其 0.5 threshold 或 coverage。",
            "",
            "| Domain | Samples | Mean similarity | Train-seen scaffold | AUROC | MCC | Accuracy | TN / FP / FN / TP |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for name, row in domain_results.items():
            auroc, mcc, confusion = markdown_metrics(row)
            metrics = row["metrics"]
            accuracy = "null" if metrics is None else f"{metrics['accuracy']:.6f}"
            mean_similarity = "null" if row["mean_similarity"] is None else f"{row['mean_similarity']:.6f}"
            domain_lines.append(
                f"| {name} | {row['sample_count']} | {mean_similarity} | {row['scaffold_seen_count']} | "
                f"{auroc} | {mcc} | {accuracy} | {confusion} |"
            )
        domain_lines.extend(
            [
                "",
                "此 domain 分层是 post-hoc 描述，不是经过外测优化的部署拒答规则。任何未来规则必须在 development 数据上预注册。",
                "",
            ]
        )
        (temporary_dir / "domain_aware_performance.md").write_text(
            "\n".join(domain_lines), encoding="utf-8"
        )
        if {path.name for path in temporary_dir.iterdir()} != OUTPUT_FILES:
            raise AssertionError("post-hoc diagnostic 输出集合不正确")
        temporary_dir.replace(args.output_dir)
    except Exception:
        import shutil

        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    print(json.dumps({"output_dir": str(args.output_dir), "external_access": "post_hoc_diagnostic_once"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
