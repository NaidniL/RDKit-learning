"""external 最终评估锁测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.release_reader import load_release_split  # noqa: E402


def test_external_is_rejected_before_any_release_read(tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="不得进入调参"):
        load_release_split(tmp_path, "splits/external_test.csv")
    with pytest.raises(PermissionError, match="manifest SHA-256"):
        load_release_split(
            tmp_path,
            "splits/external_test.csv",
            evaluation_mode="external_final",
        )


@pytest.mark.parametrize(
    "path",
    [
        "splits/external_test.csv",
        "splits/external_test_tautomer_clean_sensitivity.csv",
    ],
)
def test_feature_selection_style_modes_cannot_receive_external(
    tmp_path: Path, path: str
) -> None:
    for mode in (
        "feature_selection",
        "hyperparameter_search",
        "threshold_selection",
        "early_stopping",
        "calibration",
        "model_selection",
    ):
        with pytest.raises(PermissionError):
            load_release_split(tmp_path, path, evaluation_mode=mode)
