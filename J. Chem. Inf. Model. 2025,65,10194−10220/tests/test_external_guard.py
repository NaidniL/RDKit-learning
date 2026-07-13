from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.evaluation_guard import (  # noqa: E402
    ExternalEvaluationUnlock,
    assert_no_external_references,
    assert_split_access,
)
from modeling.experiment_config import ExperimentConfig  # noqa: E402


@pytest.mark.parametrize(
    "stage",
    [
        "training",
        "feature_selection",
        "hyperparameter_search",
        "threshold_selection",
        "early_stopping",
        "calibration",
        "model_selection",
    ],
)
def test_every_model_development_stage_rejects_external(stage: str) -> None:
    with pytest.raises(PermissionError, match="不得读取 external"):
        assert_split_access("splits/external_test.csv", stage=stage)


def test_external_final_requires_a_separate_explicit_unlock() -> None:
    with pytest.raises(PermissionError, match="尚未解锁"):
        ExternalEvaluationUnlock("0" * 64).require_approved()
    with pytest.raises(PermissionError, match="external"):
        assert_no_external_references(["external_test.csv"])
    with pytest.raises(PermissionError, match="external"):
        ExperimentConfig(
            model="dummy",
            feature_sets=("ecfp4",),
            model_params={"note": "external_test.csv"},
        )
