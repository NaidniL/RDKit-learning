#!/usr/bin/env python3
"""模型批次 1 CLI：开发训练，或以冻结配置重训 final artifact。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import rdkit  # noqa: E402
import sklearn  # noqa: E402
from scipy import sparse  # noqa: E402

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
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
from modeling.final_artifact import (  # noqa: E402
    FINAL_ARTIFACT_FILES,
    build_final_training_manifest,
    load_canonical_final_config,
    validate_frozen_final_config,
    write_feature_manifest,
    write_final_training_manifest,
)
from modeling.external_final import (  # noqa: E402
    EXTERNAL_FINAL_FILES,
    PRIMARY_EXTERNAL_PATH,
    build_external_evaluation_manifest,
    sha256_json_rows,
    verify_final_artifact_manifest,
    write_external_evaluation_manifest,
)
from modeling.featurizers import feature_manifest, featurize_smiles  # noqa: E402
from modeling.metrics import binary_confusion_counts, binary_metrics  # noqa: E402
from modeling.evaluation_guard import ExternalEvaluationUnlock, assert_split_access  # noqa: E402
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


def _development_parser() -> argparse.ArgumentParser:
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
    return parser


def _freeze_final_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="只用 train+validation 重训已冻结的 final artifact；external 永不读取。"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--fit-split",
        choices=["train_validation"],
        required=True,
        help="最终模型只能重训 train+validation",
    )
    parser.add_argument(
        "--no-external",
        action="store_true",
        required=True,
        help="必须显式确认 external 仍被拒绝读取",
    )
    parser.add_argument(
        "--releases-root",
        type=Path,
        default=ROOT / "releases" / "dataset_assembly",
        help="必须是 releases/dataset_assembly（不会接受 CSV 或 data/splits 路径）",
    )
    return parser


def _external_final_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="一次性评估已独立审核的 final artifact；只读取 primary external split。"
    )
    parser.add_argument(
        "--model",
        type=Path,
        required=True,
        help="models/final_model_v1/training_manifest.json",
    )
    parser.add_argument(
        "--releases-root",
        type=Path,
        default=ROOT / "releases" / "dataset_assembly",
        help="必须是 releases/dataset_assembly",
    )
    return parser


def parse_args() -> argparse.Namespace:
    if len(sys.argv) > 1 and sys.argv[1] == "freeze-final":
        args = _freeze_final_parser().parse_args(sys.argv[2:])
        args.command = "freeze-final"
        return args
    if len(sys.argv) > 1 and sys.argv[1] == "external-final":
        args = _external_final_parser().parse_args(sys.argv[2:])
        args.command = "external-final"
        return args
    args = _development_parser().parse_args()
    args.command = "development"
    return args


def runtime_signature() -> dict[str, str]:
    signature = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scikit_learn": sklearn.__version__,
        "rdkit": rdkit.__version__,
    }
    try:
        import lightgbm

        signature["lightgbm"] = lightgbm.__version__
    except ImportError:
        signature["lightgbm"] = "unavailable"
    return signature


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


def _prepare_final_output(output_dir: Path) -> Path:
    """最终 artifact 是不可变目录；拒绝覆盖或混入任何旧文件。"""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"final artifact 已存在，拒绝覆盖：{output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=".final_model_v1.", dir=output_dir.parent))


def _commit_final_output(temporary_dir: Path, output_dir: Path) -> None:
    if {path.name for path in temporary_dir.iterdir()} != FINAL_ARTIFACT_FILES:
        raise AssertionError("final artifact 临时目录包含禁止或缺失文件")
    if output_dir.exists():
        output_dir.rmdir()
    os.replace(temporary_dir, output_dir)


def _audit_passed() -> bool:
    report = ROOT / "reports" / "modeling" / "final_artifact_independent_audit.md"
    return report.is_file() and "状态：`PASS`。" in report.read_text(encoding="utf-8")


def _commit_external_output(temporary_dir: Path, output_dir: Path) -> None:
    if {path.name for path in temporary_dir.iterdir()} != EXTERNAL_FINAL_FILES:
        raise AssertionError("external-final 临时目录包含禁止或缺失文件")
    if output_dir.exists():
        raise FileExistsError(f"external-final 已完成，拒绝重复读取：{output_dir}")
    os.replace(temporary_dir, output_dir)


def freeze_final(args: argparse.Namespace) -> int:
    config, config_sha256 = load_canonical_final_config(args.config)
    validate_frozen_final_config(config)
    if args.fit_split != "train_validation" or not args.no_external:
        raise PermissionError("freeze-final 必须使用 --fit-split train_validation --no-external")

    release = load_formal_release_metadata_without_external_reads(args.releases_root)
    gc.collect()
    # 此 loader 只打开并逐次校验 train.csv 与 validation.csv，不会接触 CV 或 external split。
    splits = load_train_validation_splits(release)
    rows = [*splits.train, *splits.validation]
    matrix = featurize_smiles((str(row["canonical_smiles"]) for row in rows), ("rdkit_descriptors", "physicochemical"))
    labels = np.asarray([int(row["normalized_label"]) for row in rows])
    if len(rows) != len(labels) or set(labels) != {0, 1}:
        raise ValueError("train+validation 必须严格对齐且包含二元类别")

    config_for_estimator = ExperimentConfig(
        model="lightgbm",
        feature_sets=("rdkit_descriptors", "physicochemical"),
        seed=int(config["random_state"]),
        tuning=False,
        model_params=dict(config["selected_params"]),
        cv_protocol="train_tuning_cv",
        selection_metric="auroc",
        threshold=float(config["threshold"]),
    )
    estimator = build_estimator(
        config_for_estimator,
        binary_indices=matrix.binary_indices,
        descriptor_indices=matrix.descriptor_indices,
    ).fit(matrix.values, labels)
    preprocessing = estimator.named_steps["preprocess"]
    model = estimator.named_steps["model"]
    model_params = model.get_params(deep=False)
    required_model_params = {
        **dict(config["selected_params"]),
        "random_state": int(config["random_state"]),
        "n_jobs": int(config["n_jobs"]),
        "deterministic": bool(config["deterministic"]),
    }
    if any(model_params.get(key) != value for key, value in required_model_params.items()):
        raise AssertionError("已训练 LightGBM 参数与冻结配置不一致")

    output_dir = ROOT / "models" / "final_model_v1"
    temporary_dir = _prepare_final_output(output_dir)
    try:
        model_path = temporary_dir / "model.pkl"
        preprocessing_path = temporary_dir / "preprocessing.pkl"
        joblib.dump(model, model_path)
        joblib.dump(preprocessing, preprocessing_path)
        feature_sha = write_feature_manifest(temporary_dir / "feature_manifest.json", matrix)
        manifest = build_final_training_manifest(
            final_model_config_sha256=config_sha256,
            release_id=release.release_id,
            dataset_manifest_sha256=release.manifest_sha256,
            train_artifact=release.artifact_metadata("splits/primary_reproduction/train.csv"),
            validation_artifact=release.artifact_metadata("splits/primary_reproduction/validation.csv"),
            labels=labels,
            matrix=matrix,
            preprocessing=preprocessing,
            lightgbm_params=model_params,
            runtime=runtime_signature(),
            revision=code_revision(),
            model_path=model_path,
            preprocessing_path=preprocessing_path,
            feature_manifest_sha256=feature_sha,
        )
        write_final_training_manifest(temporary_dir / "training_manifest.json", manifest)
        (temporary_dir / "training.log").write_text(
            "freeze-final completed\nfit_split=train_validation\nexternal_access=denied\n",
            encoding="utf-8",
        )
        _commit_final_output(temporary_dir, output_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    print(json.dumps({"output_dir": str(output_dir), "external_access": "denied"}, sort_keys=True))
    return 0


def external_final(args: argparse.Namespace) -> int:
    expected_manifest = (ROOT / "models" / "final_model_v1" / "training_manifest.json").resolve()
    manifest_path = args.model.resolve()
    if manifest_path != expected_manifest:
        raise PermissionError("external-final 只接受 models/final_model_v1/training_manifest.json")
    if not _audit_passed():
        raise PermissionError("final artifact 独立审核未通过，external-final 仍被锁定")
    training_manifest = verify_final_artifact_manifest(manifest_path)
    unlock = ExternalEvaluationUnlock(
        frozen_experiment_manifest_sha256=sha256_file(manifest_path), approved=True
    )
    unlock.require_approved()
    output_dir = ROOT / "reports" / "modeling" / "final_external_evaluation_v1"
    if output_dir.exists():
        raise FileExistsError(f"external-final 已完成，拒绝重复读取：{output_dir}")

    # 显式 external_final 闸门后，只打开并校验 primary external CSV 本身。
    assert_split_access(PRIMARY_EXTERNAL_PATH, stage="external_final")
    release = load_formal_release_metadata_without_external_reads(args.releases_root)
    if release.manifest_sha256 != training_manifest["dataset_manifest_sha256"]:
        raise ValueError("当前 release manifest 与冻结 final artifact 不一致")
    if release.release_id != training_manifest["dataset_release_id"]:
        raise ValueError("当前 release ID 与冻结 final artifact 不一致")
    external_rows = release.read_csv(PRIMARY_EXTERNAL_PATH)
    matrix = featurize_smiles(
        (str(row["canonical_smiles"]) for row in external_rows),
        ("rdkit_descriptors", "physicochemical"),
    )
    if list(matrix.feature_names) != training_manifest["descriptor_list"]:
        raise ValueError("external 特征列与冻结 final artifact 不一致")
    labels = np.asarray([int(row["normalized_label"]) for row in external_rows])
    if len(labels) != len(external_rows) or not set(labels) <= {0, 1}:
        raise ValueError("external labels 不合法")
    model = joblib.load(manifest_path.parent / "model.pkl")
    preprocessing = joblib.load(manifest_path.parent / "preprocessing.pkl")
    probability = predict_probability(model, preprocessing.transform(matrix.values))
    metrics = binary_metrics(labels, probability, threshold=0.5)
    confusion = binary_confusion_counts(labels, probability, threshold=0.5)
    prediction_rows = [
        {
            "compound_id": str(row["compound_id"]),
            "normalized_label": int(label),
            "probability": float(value),
        }
        for row, label, value in zip(external_rows, labels, probability, strict=True)
    ]

    temporary_dir = Path(tempfile.mkdtemp(prefix=".final_external_v1.", dir=output_dir.parent))
    try:
        external_artifact = release.artifact_metadata(PRIMARY_EXTERNAL_PATH)
        manifest = build_external_evaluation_manifest(
            training_manifest_path=manifest_path,
            training_manifest=training_manifest,
            external_artifact=external_artifact,
            metrics=metrics,
            confusion=confusion,
            prediction_digest=sha256_json_rows(prediction_rows),
            prediction_rows=len(prediction_rows),
            performed_at_utc=datetime.now(timezone.utc).isoformat(),
            code_revision=code_revision(),
            runtime_signature=runtime_signature(),
        )
        write_external_evaluation_manifest(
            temporary_dir / "external_evaluation_manifest.json", manifest
        )
        markdown = [
            "# Final external evaluation v1",
            "",
            "状态：`COMPLETE`。primary external 仅评估一次；未改动模型、特征、预处理或阈值。",
            "",
            "## Locked inputs",
            "",
            f"- model training manifest SHA-256: `{manifest['approval']['model_training_manifest_sha256']}`",
            f"- dataset release: `{manifest['dataset_release_id']}`",
            f"- dataset manifest SHA-256: `{manifest['dataset_manifest_sha256']}`",
            f"- external split SHA-256: `{manifest['external_split']['sha256']}`",
            f"- samples: `{manifest['external_split']['rows']}`",
            f"- threshold: `{manifest['threshold']}`",
            "",
            "## Aggregate metrics",
            "",
            "| Metric | Value |",
            "|---|---:|",
            *[
                f"| {name} | {('null' if value is None else f'{value:.6f}')} |"
                for name, value in manifest["external_metrics"].items()
            ],
            "",
            "## Confusion counts",
            "",
            *[f"- {name}: `{value}`" for name, value in manifest["external_confusion"].items()],
            "",
            "未写出 external prediction 文件；仅在 manifest 记录 canonical prediction digest。",
            "",
        ]
        (temporary_dir / "external_evaluation.md").write_text("\n".join(markdown), encoding="utf-8")
        _commit_external_output(temporary_dir, output_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    print(json.dumps({"output_dir": str(output_dir), "external_access": "granted_final_once"}, sort_keys=True))
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "freeze-final":
        return freeze_final(args)
    if args.command == "external-final":
        return external_final(args)
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
