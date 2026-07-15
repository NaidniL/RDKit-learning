"""二分类指标；external-final 只在 final artifact 锁定后调用。"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)


def binary_metrics(
    y_true: Sequence[int], y_probability: Sequence[float], *, threshold: float = 0.5
) -> dict[str, float | None]:
    """返回不含预测明细/混淆矩阵的聚合指标。"""

    truth = np.asarray(y_true, dtype=int)
    probability = np.asarray(y_probability, dtype=float)
    if truth.ndim != 1 or probability.ndim != 1 or len(truth) != len(probability):
        raise ValueError("y_true 与 y_probability 必须是一维且长度一致")
    if len(truth) == 0 or not np.isin(truth, [0, 1]).all():
        raise ValueError("y_true 必须是非空二分类标签")
    if not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
        raise ValueError("概率必须为 [0, 1] 的有限值")
    predicted = (probability >= threshold).astype(int)
    class_count = len(np.unique(truth))
    auc: float | None = None
    if class_count == 2:
        auc = float(roc_auc_score(truth, probability))
    auprc: float | None = None
    if class_count == 2:
        auprc = float(average_precision_score(truth, probability, pos_label=1))
    # sklearn 对单类样本会发出混淆矩阵形状 warning；此时只能报告其唯一类上的
    # 准确率，不能伪造 AUROC。该分支主要服务于小型单折 sanity check。
    balanced_accuracy = (
        float(balanced_accuracy_score(truth, predicted))
        if class_count == 2
        else float(accuracy_score(truth, predicted))
    )
    positive_count = int(np.count_nonzero(truth == 1))
    negative_count = int(np.count_nonzero(truth == 0))
    sensitivity: float | None = None
    specificity: float | None = None
    if positive_count:
        sensitivity = float(np.count_nonzero((truth == 1) & (predicted == 1)) / positive_count)
    if negative_count:
        specificity = float(np.count_nonzero((truth == 0) & (predicted == 0)) / negative_count)
    true_positive = int(np.count_nonzero((truth == 1) & (predicted == 1)))
    true_negative = int(np.count_nonzero((truth == 0) & (predicted == 0)))
    false_positive = int(np.count_nonzero((truth == 0) & (predicted == 1)))
    false_negative = int(np.count_nonzero((truth == 1) & (predicted == 0)))
    denominator = float(
        (true_positive + false_positive)
        * (true_positive + false_negative)
        * (true_negative + false_positive)
        * (true_negative + false_negative)
    ) ** 0.5
    mcc = (
        float((true_positive * true_negative - false_positive * false_negative) / denominator)
        if denominator
        else 0.0
    )
    return {
        "auroc": auc,
        "auprc": auprc,
        "accuracy": float(accuracy_score(truth, predicted)),
        "balanced_accuracy": balanced_accuracy,
        "precision": float(precision_score(truth, predicted, zero_division=0)),
        "recall": float(recall_score(truth, predicted, zero_division=0)),
        "f1": float(f1_score(truth, predicted, zero_division=0)),
        "brier": float(brier_score_loss(truth, probability)),
        "log_loss": float(log_loss(truth, probability, labels=[0, 1])),
        "sensitivity": sensitivity,
        "specificity": specificity,
        # 分母退化时固定为 0，避免 sklearn 单类样本 warning。
        "mcc": mcc,
    }


def binary_confusion_counts(
    y_true: Sequence[int], y_probability: Sequence[float], *, threshold: float = 0.5
) -> dict[str, int]:
    """返回聚合混淆计数；不写任何样本级预测。"""

    truth = np.asarray(y_true, dtype=int)
    probability = np.asarray(y_probability, dtype=float)
    if truth.ndim != 1 or probability.ndim != 1 or len(truth) != len(probability):
        raise ValueError("y_true 与 y_probability 必须是一维且长度一致")
    predicted = (probability >= threshold).astype(int)
    return {
        "true_negative": int(np.count_nonzero((truth == 0) & (predicted == 0))),
        "false_positive": int(np.count_nonzero((truth == 0) & (predicted == 1))),
        "false_negative": int(np.count_nonzero((truth == 1) & (predicted == 0))),
        "true_positive": int(np.count_nonzero((truth == 1) & (predicted == 1))),
    }
