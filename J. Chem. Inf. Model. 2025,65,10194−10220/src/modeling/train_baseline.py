"""受控的 Dummy / LR / RF / LightGBM / HistGB 基线训练。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import warnings

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_selection import VarianceThreshold
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, PredefinedSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .experiment_config import ExperimentConfig
from .metrics import binary_metrics
from .split_loader import TrainTuningCVFolds


@dataclass(frozen=True)
class TrainingResult:
    estimator: Any
    train_cv_metrics: dict[str, float | None]
    best_params: dict[str, Any]


def _logistic_preprocessor(
    binary_indices: tuple[int, ...], descriptor_indices: tuple[int, ...]
) -> ColumnTransformer | str:
    """指纹保持原样；仅连续 descriptor 在训练折内 impute/scale。"""

    if not descriptor_indices:
        return "passthrough"
    descriptor_pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("remove_constant", VarianceThreshold()),
            ("scale", StandardScaler()),
        ]
    )
    transformers: list[tuple[str, Any, tuple[int, ...]]] = [
        ("descriptors", descriptor_pipeline, descriptor_indices)
    ]
    if binary_indices:
        transformers.insert(0, ("fingerprints", "passthrough", binary_indices))
    return ColumnTransformer(transformers, remainder="drop", sparse_threshold=0.3)


def _tree_preprocessor(
    binary_indices: tuple[int, ...], descriptor_indices: tuple[int, ...]
) -> ColumnTransformer | str:
    """树模型不缩放；连续 descriptor 仍只在训练折内 impute。"""

    if not descriptor_indices:
        return "passthrough"
    descriptor_pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("remove_constant", VarianceThreshold()),
        ]
    )
    transformers: list[tuple[str, Any, tuple[int, ...]]] = [
        ("descriptors", descriptor_pipeline, descriptor_indices)
    ]
    if binary_indices:
        transformers.insert(0, ("fingerprints", "passthrough", binary_indices))
    return ColumnTransformer(transformers, remainder="drop", sparse_threshold=0.3)


def build_estimator(
    config: ExperimentConfig,
    *,
    binary_indices: tuple[int, ...] = (),
    descriptor_indices: tuple[int, ...] = (),
) -> Any:
    params = config.resolved_model_parameters()
    if config.model == "dummy":
        return DummyClassifier(strategy=config.dummy_strategy, random_state=config.seed)
    if config.model == "logistic_regression":
        return Pipeline(
            [
                ("preprocess", _logistic_preprocessor(binary_indices, descriptor_indices)),
                ("model", LogisticRegression(**params)),
            ]
        )
    if config.model == "random_forest":
        defaults: dict[str, Any] = {"random_state": config.seed, "n_estimators": 500, "n_jobs": 1}
        defaults.update(params)
        return Pipeline(
            [
                ("preprocess", _tree_preprocessor(binary_indices, descriptor_indices)),
                ("model", RandomForestClassifier(**defaults)),
            ]
        )
    if config.model == "hist_gradient_boosting":
        return Pipeline(
            [
                ("preprocess", _tree_preprocessor(binary_indices, descriptor_indices)),
                ("model", HistGradientBoostingClassifier(random_state=config.seed, **params)),
            ]
        )
    if config.model == "lightgbm":
        try:
            from lightgbm import LGBMClassifier
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("LightGBM 未安装；请使用 requirements-lock.txt 环境") from exc
        defaults = {
            "random_state": config.seed,
            "n_estimators": 300,
            "n_jobs": 1,
            "deterministic": True,
            "verbosity": -1,
        }
        defaults.update(params)
        return Pipeline(
            [
                ("preprocess", _tree_preprocessor(binary_indices, descriptor_indices)),
                ("model", LGBMClassifier(**defaults)),
            ]
        )
    raise AssertionError("ExperimentConfig 已验证 model")


def _probabilities(estimator: Any, x: np.ndarray) -> np.ndarray:
    probability = np.asarray(estimator.predict_proba(x), dtype=float)
    classes = list(estimator.classes_)
    if 1 not in classes:
        return np.zeros(len(x), dtype=float)
    return probability[:, classes.index(1)]


def _fold_vector(folds: TrainTuningCVFolds, train_ids: list[str]) -> np.ndarray:
    if folds.purpose != "train_tuning_only":
        raise PermissionError("只有 train_tuning_cv_folds 可用于超参数搜索")
    mapping = {str(row["compound_id"]): int(row["fold_id"]) for row in folds.rows}
    if len(mapping) != len(train_ids) or set(mapping) != set(train_ids):
        raise ValueError("train_tuning_cv_folds 必须与 fixed train 一一对应")
    return np.asarray([mapping[item] for item in train_ids], dtype=int)


def _default_grid(config: ExperimentConfig) -> dict[str, list[Any]]:
    if config.model == "logistic_regression":
        return {"model__C": [0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0]}
    if config.model == "random_forest":
        return {
            "model__n_estimators": [300, 500],
            "model__max_features": ["sqrt", "log2"],
            "model__min_samples_leaf": [1, 2, 5],
            "model__class_weight": [None, "balanced"],
        }
    if config.model == "lightgbm":
        return {
            "model__num_leaves": [15, 31, 63],
            "model__learning_rate": [0.03, 0.1],
            "model__n_estimators": [100, 300],
            "model__min_child_samples": [10, 20, 50],
            "model__reg_lambda": [0, 1, 10],
        }
    if config.model == "hist_gradient_boosting":
        return {"model__max_depth": [None, 8], "model__learning_rate": [0.03, 0.1]}
    return {}


def fit_with_train_tuning_cv(
    config: ExperimentConfig,
    x_train: np.ndarray,
    y_train: np.ndarray,
    train_ids: list[str],
    tuning_folds: TrainTuningCVFolds,
    binary_indices: tuple[int, ...] = (),
    descriptor_indices: tuple[int, ...] = (),
) -> TrainingResult:
    """所有超参选择严格使用 train 内指定 folds，随后在完整 train 上重训。"""

    estimator = build_estimator(
        config,
        binary_indices=binary_indices,
        descriptor_indices=descriptor_indices,
    )
    if not isinstance(tuning_folds, TrainTuningCVFolds):
        raise PermissionError("调参必须传入 split loader 产生的 train_tuning_cv_folds")
    fold_vector = _fold_vector(tuning_folds, train_ids)
    cv = PredefinedSplit(fold_vector)
    best_params: dict[str, Any] = {}
    selected = estimator
    if config.tuning and _default_grid(config):
        search = GridSearchCV(
            estimator,
            _default_grid(config),
            scoring="roc_auc",
            cv=cv,
            n_jobs=1,
            refit=True,
            error_score="raise",
        )
        with warnings.catch_warnings():
            warnings.filterwarnings("error", category=ConvergenceWarning)
            search.fit(x_train, y_train)
        selected = search.best_estimator_
        best_params = dict(search.best_params_)
    else:
        with warnings.catch_warnings():
            warnings.filterwarnings("error", category=ConvergenceWarning)
            selected.fit(x_train, y_train)

    # 固定 folds 的 OOF 概率只用于报告 train CV performance，不写出预测文件。
    oof = np.zeros(len(y_train), dtype=float)
    for train_index, test_index in cv.split():
        fold_model = build_estimator(
            config,
            binary_indices=binary_indices,
            descriptor_indices=descriptor_indices,
        )
        if best_params:
            fold_model.set_params(**best_params)
        with warnings.catch_warnings():
            warnings.filterwarnings("error", category=ConvergenceWarning)
            fold_model.fit(x_train[train_index], y_train[train_index])
        oof[test_index] = _probabilities(fold_model, x_train[test_index])
    return TrainingResult(
        estimator=selected,
        train_cv_metrics=binary_metrics(y_train, oof, threshold=config.threshold),
        best_params=best_params,
    )


def predict_probability(estimator: Any, x: np.ndarray) -> np.ndarray:
    return _probabilities(estimator, x)
