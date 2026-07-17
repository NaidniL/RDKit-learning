"""Development-only helpers for aggregate selective-prediction diagnostics."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


V2_OUTPUT_SCHEMA_VERSION = "v2_output_contract_v1"
V2_OUTPUT_FIELDS = (
    "schema_version",
    "prediction",
    "decision_reason",
    "review_required",
)


def validate_probability_matrix(probabilities: Sequence[Sequence[float]]) -> np.ndarray:
    """Return an ``n_samples × n_models`` finite probability matrix."""

    matrix = np.asarray(probabilities, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] < 2:
        raise ValueError("probability matrix 必须为非空 n_samples × n_models 矩阵")
    if not np.isfinite(matrix).all() or np.any((matrix < 0) | (matrix > 1)):
        raise ValueError("probability matrix 必须只包含 [0, 1] 的有限值")
    return matrix


def hard_predictions(probabilities: Sequence[Sequence[float]], *, threshold: float) -> np.ndarray:
    matrix = validate_probability_matrix(probabilities)
    if not 0 < threshold < 1:
        raise ValueError("threshold 必须在 (0, 1) 内")
    return (matrix >= threshold).astype(int)


def unanimity_mask(probabilities: Sequence[Sequence[float]], *, threshold: float) -> np.ndarray:
    """Return samples on which every member emits the same hard call."""

    calls = hard_predictions(probabilities, threshold=threshold)
    return np.all(calls == calls[:, [0]], axis=1)


def v2_output_records(
    probabilities: Sequence[Sequence[float]], *, threshold: float
) -> list[dict[str, str | bool]]:
    """Return the frozen v2 three-way output for each member-probability row.

    ``inconclusive`` is a deliberate abstention caused by member disagreement;
    it is not a binary prediction and therefore requires review. This helper
    implements the output contract only. It does not select models, fit them,
    or apply an applicability-domain rejection rule.
    """

    calls = hard_predictions(probabilities, threshold=threshold)
    positive = np.all(calls == 1, axis=1)
    negative = np.all(calls == 0, axis=1)
    records: list[dict[str, str | bool]] = []
    for is_positive, is_negative in zip(positive, negative, strict=True):
        if is_positive:
            prediction = "carcinogen"
            reason = "unanimous_carcinogen"
            review_required = False
        elif is_negative:
            prediction = "noncarcinogen"
            reason = "unanimous_noncarcinogen"
            review_required = False
        else:
            prediction = "inconclusive"
            reason = "member_disagreement"
            review_required = True
        records.append(
            {
                "schema_version": V2_OUTPUT_SCHEMA_VERSION,
                "prediction": prediction,
                "decision_reason": reason,
                "review_required": review_required,
            }
        )
    return records


def model_vote_agreement(
    probabilities: Sequence[Sequence[float]], *, threshold: float
) -> np.ndarray:
    """Return the fraction of member hard calls supporting the majority class."""

    calls = hard_predictions(probabilities, threshold=threshold)
    positive_votes = calls.sum(axis=1)
    return np.maximum(positive_votes, calls.shape[1] - positive_votes) / calls.shape[1]


def confidence_scores(probabilities: Sequence[Sequence[float]], *, threshold: float) -> dict[str, np.ndarray]:
    """Return fixed exploratory ranking scores for selective prediction.

    Higher scores are retained first.  They are diagnostics, not learned policy
    parameters: no labels are used in the ranking.
    """

    matrix = validate_probability_matrix(probabilities)
    margins = np.abs(matrix - threshold)
    return {
        "mean_margin": margins.mean(axis=1),
        "minimum_margin": margins.min(axis=1),
        "hard_vote_agreement": model_vote_agreement(matrix, threshold=threshold),
    }


def top_coverage_mask(
    primary_score: Sequence[float],
    *,
    coverage: float,
    secondary_score: Sequence[float] | None = None,
) -> np.ndarray:
    """Select the highest-scoring deterministic prefix for a requested coverage.

    The selected count is ``ceil(coverage × n)``. Ties are resolved by the
    supplied secondary score, then by the original validated split row order.
    """

    primary = np.asarray(primary_score, dtype=float)
    if primary.ndim != 1 or not len(primary) or not np.isfinite(primary).all():
        raise ValueError("primary_score 必须为非空有限一维数组")
    if not 0 < coverage <= 1:
        raise ValueError("coverage 必须在 (0, 1] 内")
    secondary = np.zeros(len(primary), dtype=float)
    if secondary_score is not None:
        secondary = np.asarray(secondary_score, dtype=float)
        if secondary.shape != primary.shape or not np.isfinite(secondary).all():
            raise ValueError("secondary_score 必须与 primary_score 同形且有限")
    indices = np.arange(len(primary))
    order = np.lexsort((indices, -secondary, -primary))
    selected = np.zeros(len(primary), dtype=bool)
    selected[order[: int(np.ceil(coverage * len(primary)))]] = True
    return selected


def error_pattern_counts(
    y_true: Sequence[int], probabilities: Sequence[Sequence[float]], *, threshold: float
) -> dict[str, int]:
    """Aggregate per-member and multi-member hard-call errors without IDs."""

    truth = np.asarray(y_true, dtype=int)
    calls = hard_predictions(probabilities, threshold=threshold)
    if truth.ndim != 1 or len(truth) != len(calls) or not np.isin(truth, [0, 1]).all():
        raise ValueError("y_true 必须是与概率矩阵对齐的二分类标签")
    errors = calls != truth[:, None]
    error_count = errors.sum(axis=1)
    return {
        "any_member_wrong": int(np.count_nonzero(error_count >= 1)),
        "at_least_two_members_wrong": int(np.count_nonzero(error_count >= 2)),
        "all_members_wrong": int(np.count_nonzero(error_count == calls.shape[1])),
    }
