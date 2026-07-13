from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.experiment_config import ExperimentConfig  # noqa: E402
from modeling.train_baseline import _default_grid, build_estimator  # noqa: E402


def test_random_forest_imputes_descriptor_nan_without_scaling() -> None:
    estimator = build_estimator(
        ExperimentConfig(model="random_forest", feature_sets=("rdkit_descriptors",)),
        descriptor_indices=(0, 1),
    )
    estimator.fit(np.asarray([[1.0, np.nan], [2.0, 3.0], [3.0, 4.0], [4.0, 5.0]]), [0, 1, 0, 1])
    descriptors = estimator.named_steps["preprocess"].named_transformers_["descriptors"]
    assert "scale" not in descriptors.named_steps
    assert estimator.predict_proba(np.asarray([[5.0, np.nan]])).shape == (1, 2)


def test_tree_grids_are_pre_registered() -> None:
    rf_grid = _default_grid(ExperimentConfig(model="random_forest", feature_sets=("ecfp4",)))
    lgbm_grid = _default_grid(ExperimentConfig(model="lightgbm", feature_sets=("ecfp4",)))
    assert rf_grid["model__class_weight"] == [None, "balanced"]
    assert lgbm_grid["model__num_leaves"] == [15, 31, 63]
