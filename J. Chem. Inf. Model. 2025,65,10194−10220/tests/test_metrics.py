from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.metrics import binary_confusion_counts, binary_metrics  # noqa: E402


def test_binary_metrics_include_auc_for_two_classes() -> None:
    result = binary_metrics([0, 0, 1, 1], [0.1, 0.4, 0.6, 0.9])
    assert result["auroc"] == 1.0
    assert result["accuracy"] == 1.0
    assert "confusion_matrix" not in result
    assert result["sensitivity"] == 1.0
    assert result["specificity"] == 1.0
    assert result["mcc"] == 1.0
    assert result["auprc"] == 1.0
    assert result["log_loss"] > 0


def test_binary_metrics_handles_single_class_without_fake_auc() -> None:
    result = binary_metrics([1, 1], [0.6, 0.8])
    assert result["auroc"] is None
    assert result["sensitivity"] == 1.0
    assert result["specificity"] is None
    assert result["mcc"] == 0.0
    with pytest.raises(ValueError):
        binary_metrics([0, 1], [1.5, 0.1])


def test_development_confusion_counts_are_named_by_class_role() -> None:
    assert binary_confusion_counts([0, 0, 1, 1], [0.1, 0.9, 0.1, 0.9]) == {
        "true_negative": 1,
        "false_positive": 1,
        "false_negative": 1,
        "true_positive": 1,
    }
