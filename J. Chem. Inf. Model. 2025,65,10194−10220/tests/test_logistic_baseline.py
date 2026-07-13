from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.experiment_config import ExperimentConfig  # noqa: E402
from modeling.train_baseline import build_estimator  # noqa: E402


def test_logistic_uses_train_only_descriptor_preprocessing() -> None:
    config = ExperimentConfig(model="logistic_regression", feature_sets=("ecfp4",))
    estimator = build_estimator(config, binary_indices=(0, 1), descriptor_indices=(2, 3))
    x_train = np.asarray([[0, 1, 1.0, 10.0], [1, 0, 3.0, 20.0], [0, 1, 5.0, 30.0], [1, 0, 7.0, 40.0]])
    y_train = np.asarray([0, 1, 0, 1])
    estimator.fit(x_train, y_train)
    model = estimator.named_steps["model"]
    assert model.solver == "liblinear"
    assert model.penalty == "l2"
    assert model.max_iter == 5_000
    descriptor_pipeline = estimator.named_steps["preprocess"].named_transformers_["descriptors"]
    assert np.array_equal(descriptor_pipeline.named_steps["impute"].statistics_, [4.0, 25.0])
    assert estimator.predict_proba(np.asarray([[1, 0, 1000.0, 2000.0]])).shape == (1, 2)
