#!/usr/bin/env python3
"""模型批次 1 CLI：只训练和报告 development 数据。"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import rdkit  # noqa: E402
import sklearn  # noqa: E402
from scipy import sparse  # noqa: E402

from modeling.dataset_release_reader import (  # noqa: E402
    load_release_after_full_verification,
    verify_full_release_in_subprocess,
)
from modeling.experiment_config import ExperimentConfig  # noqa: E402
from modeling.experiment_manifest import (  # noqa: E402
    build_experiment_manifest,
    sha256_file,
    validation_prediction_digest,
    write_experiment_manifest,
    write_json_artifact,
)
from modeling.featurizers import feature_manifest, featurize_smiles  # noqa: E402
from modeling.metrics import binary_confusion_counts, binary_metrics  # noqa: E402
from modeling.sanity_checks import (  # noqa: E402
    assert_most_frequent_expectations,
    assert_stratified_reproducibility,
    assert_train_validation_alignment,
    class_counts,
)
from modeling.split_loader import (  # noqa: E402
    load_development_splits,
    load_train_validation_splits,
)
from modeling.train_baseline import (  # noqa: E402
    TrainingResult,
    build_estimator,
    fit_with_train_tuning_cv,
    predict_probability,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--releases-root",
        type=Path,
        default=ROOT / "releases" / "dataset_assembly",
        help="必须是 releases/dataset_assembly（不会接受 CSV 或 data/splits 路径）",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--model",
        choices=["dummy", "logistic_regression", "random_forest", "lightgbm", "hist_gradient_boosting"],
        default="dummy",
    )
    parser.add_argument("--features", default="ecfp4", help="逗号分隔：ecfp4,maccs,rdkit_descriptors,physicochemical")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cv", choices=["train_tuning_cv"], default="train_tuning_cv")
    parser.add_argument("--metric", choices=["auroc"], default="auroc")
    parser.add_argument(
        "--no-external",
        action="store_true",
        help="显式确认 external 保持锁定；训练默认同样拒绝 external",
    )
    parser.add_argument(
        "--dummy-strategy",
        choices=["most_frequent", "stratified"],
        default="most_frequent",
        help="DummyClassifier 体检策略；仅 --model dummy 时生效",
    )
    parser.add_argument("--tune", action="store_true", help="只使用 train_tuning_cv_folds 调参")
    parser.add_argument("--model-params-json", default="{}")
    return parser.parse_args()


def runtime_signature() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scikit_learn": sklearn.__version__,
        "rdkit": rdkit.__version__,
    }


def code_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def feature_matrix_audit(estimator: object, matrix: object, descriptor_indices: tuple[int, ...]) -> dict[str, object]:
    """记录输入布局和训练折内 descriptor 预处理结果，不写任何样本预测。"""

    shape = getattr(matrix, "shape")
    summary: dict[str, object] = {
        "input_shape": [int(shape[0]), int(shape[1])],
        "input_storage": "sparse_csr" if sparse.isspmatrix_csr(matrix) else "dense_ndarray",
        "descriptor_columns": len(descriptor_indices),
        "imputed_descriptor_columns": 0,
        "constant_descriptor_columns_removed": 0,
        "final_feature_count": None,
    }
    if descriptor_indices and not sparse.issparse(matrix):
        summary["imputed_descriptor_columns"] = int(
            np.isnan(np.asarray(matrix)[:, descriptor_indices]).any(axis=0).sum()
        )
    preprocess = getattr(estimator, "named_steps", {}).get("preprocess")
    if preprocess not in {None, "passthrough"} and descriptor_indices:
        descriptor_pipeline = preprocess.named_transformers_["descriptors"]
        support = descriptor_pipeline.named_steps["remove_constant"].get_support()
        summary["constant_descriptor_columns_removed"] = int(len(support) - support.sum())
    model = getattr(estimator, "named_steps", {}).get("model", estimator)
    summary["final_feature_count"] = int(getattr(model, "n_features_in_", shape[1]))
    return summary


def main() -> int:
    args = parse_args()
    try:
        params = json.loads(args.model_params_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--model-params-json 必须是 JSON object：{exc}") from exc
    if not isinstance(params, dict):
        raise SystemExit("--model-params-json 必须是 JSON object")
    config = ExperimentConfig(
        model=args.model,
        feature_sets=tuple(item for item in args.features.split(",") if item),
        seed=args.seed,
        tuning=args.tune,
        model_params=params,
        dummy_strategy=args.dummy_strategy,
        cv_protocol=args.cv,
        selection_metric=args.metric,
    )
    if config.model == "dummy" and config.tuning:
        raise SystemExit("Dummy sanity check 不允许调参；它只 fit train 并 evaluate validation")
    release_id, manifest_sha256 = verify_full_release_in_subprocess(args.releases_root)
    release = load_release_after_full_verification(
        args.releases_root, release_id=release_id, manifest_sha256=manifest_sha256
    )
    gc.collect()
    splits = (
        load_train_validation_splits(release)
        if config.model == "dummy"
        else load_development_splits(release)
    )
    x_train = featurize_smiles((str(row["canonical_smiles"]) for row in splits.train), config.feature_sets)
    x_validation = featurize_smiles((str(row["canonical_smiles"]) for row in splits.validation), config.feature_sets)
    y_train = np.asarray([int(row["normalized_label"]) for row in splits.train])
    y_validation = np.asarray([int(row["normalized_label"]) for row in splits.validation])
    train_ids, validation_ids = assert_train_validation_alignment(
        train_rows=splits.train,
        validation_rows=splits.validation,
        x_train=x_train.values,
        x_validation=x_validation.values,
        y_train=y_train,
        y_validation=y_validation,
    )
    if config.model == "dummy":
        estimator = build_estimator(
            config,
            binary_indices=x_train.binary_indices,
            descriptor_indices=x_train.descriptor_indices,
        ).fit(x_train.values, y_train)
        result = TrainingResult(estimator=estimator, train_cv_metrics={}, best_params={})
    else:
        result = fit_with_train_tuning_cv(
            config,
            x_train.values,
            y_train,
            train_ids,
            splits.train_tuning_cv_folds,
            binary_indices=x_train.binary_indices,
            descriptor_indices=x_train.descriptor_indices,
        )
    validation_probability = predict_probability(result.estimator, x_validation.values)
    if len(validation_probability) != len(validation_ids):
        raise ValueError("validation prediction 行数与 compound_id 不一致")
    validation_metrics = binary_metrics(y_validation, validation_probability, threshold=config.threshold)
    validation_confusion = binary_confusion_counts(
        y_validation, validation_probability, threshold=config.threshold
    )
    train_fit_metrics = binary_metrics(
        y_train,
        predict_probability(result.estimator, x_train.values),
        threshold=config.threshold,
    )
    if config.model == "dummy" and config.dummy_strategy == "most_frequent":
        assert_most_frequent_expectations(
            estimator=result.estimator,
            x_validation=x_validation.values,
            y_train=y_train,
            y_validation=y_validation,
            threshold=config.threshold,
        )
    if config.model == "dummy" and config.dummy_strategy == "stratified":
        assert_stratified_reproducibility(
            config=config,
            x_train=x_train.values,
            y_train=y_train,
            x_validation=x_validation.values,
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.output_dir / "model.joblib"
    joblib.dump(result.estimator, model_path)
    feature_path = args.output_dir / "feature_manifest.json"
    feature_sha = write_json_artifact(feature_path, feature_manifest(x_train))
    prediction_sha, prediction_rows = validation_prediction_digest(
        validation_ids,
        [int(label) for label in y_validation],
        [float(value) for value in validation_probability],
    )
    manifest = build_experiment_manifest(
        release_id=release.release_id,
        release_manifest_sha256=release.manifest_sha256,
        config=config.manifest_dict(),
        feature_manifest_sha256=feature_sha,
        feature_manifest=feature_manifest(x_train),
        model_artifact_sha256=sha256_file(model_path),
        model_artifact_bytes=model_path.stat().st_size,
        train_cv_metrics=result.train_cv_metrics,
        validation_metrics=validation_metrics,
        best_params=result.best_params,
        split_artifacts={
            "splits/primary_reproduction/train.csv": release.artifact_metadata("splits/primary_reproduction/train.csv"),
            "splits/primary_reproduction/validation.csv": release.artifact_metadata("splits/primary_reproduction/validation.csv"),
            **(
                {
                    "splits/primary_reproduction/train_tuning_cv_folds.csv": release.artifact_metadata("splits/primary_reproduction/train_tuning_cv_folds.csv")
                }
                if config.model != "dummy"
                else {}
            ),
        },
        data_summary={
            "train": {"sample_count": len(train_ids), "class_counts": class_counts(y_train)},
            "validation": {"sample_count": len(validation_ids), "class_counts": class_counts(y_validation)},
            "train_fit_metrics": train_fit_metrics,
            "feature_matrix_audit": feature_matrix_audit(
                result.estimator, x_train.values, x_train.descriptor_indices
            ),
        },
        runtime_signature=runtime_signature(),
        code_revision=code_revision(),
        validation_confusion=validation_confusion,
        validation_prediction_sha256=prediction_sha,
        validation_prediction_rows=prediction_rows,
    )
    write_experiment_manifest(args.output_dir / "experiment_manifest.json", manifest)
    print(json.dumps({"output_dir": str(args.output_dir), "validation_metrics": validation_metrics}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
