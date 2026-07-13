"""DummyClassifier 的训练链路体检断言。"""

from __future__ import annotations

from collections import Counter
from typing import Any, Sequence

import numpy as np

from .experiment_config import ExperimentConfig
from .metrics import binary_metrics
from .train_baseline import build_estimator, predict_probability


def validate_split_rows(rows: Sequence[dict[str, object]], *, split_name: str) -> list[str]:
    """验证 id/标签/结构存在且 row 顺序能安全传给特征器。"""

    ids = [str(row.get("compound_id", "")) for row in rows]
    labels = [row.get("normalized_label") for row in rows]
    if not ids or any(not item for item in ids):
        raise ValueError(f"{split_name} 缺少 compound_id")
    if len(ids) != len(set(ids)):
        raise ValueError(f"{split_name} 存在重复 compound_id")
    if any(label not in {0, 1} for label in labels):
        raise ValueError(f"{split_name} 标签必须且只能为 0/1")
    if any(not isinstance(row.get("canonical_smiles"), str) or not row["canonical_smiles"] for row in rows):
        raise ValueError(f"{split_name} 缺少 canonical_smiles")
    return ids


def assert_train_validation_alignment(
    *,
    train_rows: Sequence[dict[str, object]],
    validation_rows: Sequence[dict[str, object]],
    x_train: np.ndarray,
    x_validation: np.ndarray,
    y_train: np.ndarray,
    y_validation: np.ndarray,
) -> tuple[list[str], list[str]]:
    """保证 X/y 行数、ID 唯一性和 train/validation 成员关系不可错位。"""

    train_ids = validate_split_rows(train_rows, split_name="train")
    validation_ids = validate_split_rows(validation_rows, split_name="validation")
    if set(train_ids) & set(validation_ids):
        raise ValueError("train 与 validation 的 compound_id 不得重叠")
    if x_train.shape[0] != len(train_ids) or len(y_train) != len(train_ids):
        raise ValueError("X_train 与 y_train/compound_id 行数不对齐")
    if x_validation.shape[0] != len(validation_ids) or len(y_validation) != len(validation_ids):
        raise ValueError("X_validation 与 y_validation/compound_id 行数不对齐")
    expected_train = np.asarray([int(row["normalized_label"]) for row in train_rows])
    expected_validation = np.asarray([int(row["normalized_label"]) for row in validation_rows])
    if not np.array_equal(y_train, expected_train) or not np.array_equal(y_validation, expected_validation):
        raise ValueError("特征行顺序与 split 标签行顺序不一致")
    return train_ids, validation_ids


def class_counts(labels: Sequence[int]) -> dict[str, int]:
    counts = Counter(int(label) for label in labels)
    return {"0": counts[0], "1": counts[1]}


def assert_most_frequent_expectations(
    *,
    estimator: Any,
    x_validation: np.ndarray,
    y_train: np.ndarray,
    y_validation: np.ndarray,
    threshold: float,
) -> dict[str, float | None]:
    """验证常数预测和其 accuracy/MCC/AUROC 的精确退化行为。"""

    counts = class_counts(y_train)
    majority = 0 if counts["0"] >= counts["1"] else 1
    prediction = np.asarray(estimator.predict(x_validation), dtype=int)
    probability = predict_probability(estimator, x_validation)
    if not np.all(prediction == majority):
        raise AssertionError("most_frequent 未恒定预测 train 多数类")
    metrics = binary_metrics(y_validation, probability, threshold=threshold)
    expected_accuracy = float(np.mean(y_validation == majority))
    if metrics["accuracy"] != expected_accuracy:
        raise AssertionError("most_frequent validation accuracy 不等于多数类占比")
    if metrics["mcc"] != 0.0:
        raise AssertionError("常数预测的 MCC 应为 0")
    if len(np.unique(y_validation)) == 2 and metrics["auroc"] != 0.5:
        raise AssertionError("常数概率的 AUROC 应为 0.5")
    return metrics


def assert_stratified_reproducibility(
    *,
    config: ExperimentConfig,
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_validation: np.ndarray,
) -> None:
    """相同 seed 的 stratified Dummy 必须产生相同预测和概率。"""

    first = build_estimator(config).fit(x_train, y_train)
    second = build_estimator(config).fit(x_train, y_train)
    if not np.array_equal(first.predict(x_validation), second.predict(x_validation)):
        raise AssertionError("stratified Dummy 的相同 seed 预测不稳定")
    if not np.array_equal(predict_probability(first, x_validation), predict_probability(second, x_validation)):
        raise AssertionError("stratified Dummy 的相同 seed 概率不稳定")
