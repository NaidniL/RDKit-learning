from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.evaluation_guard import assert_split_access  # noqa: E402
from modeling.split_loader import (  # noqa: E402
    FULL_DEVELOPMENT_CV_PATHS,
    TRAIN_PATH,
    TrainTuningCVFolds,
    TUNING_FOLDS_PATH,
    VALIDATION_PATH,
)
from modeling.split_loader import FixedDevelopmentSplits  # noqa: E402


def test_default_development_paths_are_the_only_training_inputs() -> None:
    for path in (TRAIN_PATH, VALIDATION_PATH, TUNING_FOLDS_PATH):
        assert_split_access(path, stage="training")
    assert_split_access(FULL_DEVELOPMENT_CV_PATHS["stratified"], stage="training")


def test_unknown_or_external_paths_are_rejected() -> None:
    with pytest.raises(PermissionError):
        assert_split_access("data/splits/v1/train.csv", stage="training")
    with pytest.raises(PermissionError):
        assert_split_access("splits/external_test.csv", stage="hyperparameter_search")


def test_tuning_folds_carry_a_training_only_purpose() -> None:
    assert TrainTuningCVFolds([]).purpose == "train_tuning_only"
    assert FixedDevelopmentSplits([], []).train == []
