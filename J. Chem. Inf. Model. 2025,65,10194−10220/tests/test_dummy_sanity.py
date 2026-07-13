from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.experiment_config import ExperimentConfig  # noqa: E402
from modeling.sanity_checks import (  # noqa: E402
    assert_most_frequent_expectations,
    assert_stratified_reproducibility,
    assert_train_validation_alignment,
)
from modeling.train_baseline import build_estimator  # noqa: E402


def test_most_frequent_has_expected_constant_predictions() -> None:
    config = ExperimentConfig(model="dummy", feature_sets=("ecfp4",))
    x_train = np.asarray([[0.0], [1.0], [2.0], [3.0]])
    y_train = np.asarray([0, 0, 0, 1])
    x_validation = np.asarray([[4.0], [5.0], [6.0], [7.0]])
    y_validation = np.asarray([0, 0, 1, 1])
    estimator = build_estimator(config).fit(x_train, y_train)
    result = assert_most_frequent_expectations(
        estimator=estimator,
        x_validation=x_validation,
        y_train=y_train,
        y_validation=y_validation,
        threshold=0.5,
    )
    assert result["accuracy"] == 0.5
    assert result["auroc"] == 0.5
    assert result["mcc"] == 0.0


def test_stratified_dummy_is_reproducible_for_fixed_seed() -> None:
    config = ExperimentConfig(
        model="dummy", feature_sets=("ecfp4",), dummy_strategy="stratified", seed=42
    )
    assert_stratified_reproducibility(
        config=config,
        x_train=np.arange(20, dtype=float).reshape(10, 2),
        y_train=np.asarray([0, 1] * 5),
        x_validation=np.arange(12, dtype=float).reshape(6, 2),
    )


def test_alignment_rejects_overlap_and_bad_labels() -> None:
    train = [{"compound_id": "A", "canonical_smiles": "CC", "normalized_label": 0}]
    validation = [{"compound_id": "A", "canonical_smiles": "CO", "normalized_label": 1}]
    with pytest.raises(ValueError, match="不得重叠"):
        assert_train_validation_alignment(
            train_rows=train,
            validation_rows=validation,
            x_train=np.zeros((1, 1)),
            x_validation=np.zeros((1, 1)),
            y_train=np.asarray([0]),
            y_validation=np.asarray([1]),
        )
