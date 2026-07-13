"""只暴露开发集切分，不让默认训练路径接触 external。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .dataset_release_reader import DatasetRelease
from .evaluation_guard import assert_split_access


TRAIN_PATH = "splits/primary_reproduction/train.csv"
VALIDATION_PATH = "splits/primary_reproduction/validation.csv"
TUNING_FOLDS_PATH = "splits/primary_reproduction/train_tuning_cv_folds.csv"
FULL_DEVELOPMENT_CV_PATHS = {
    "stratified": "splits/full_development_stratified_cv_folds.csv",
    "scaffold": "splits/full_development_scaffold_cv_folds.csv",
}


@dataclass(frozen=True)
class DevelopmentSplits:
    train: list[dict[str, object]]
    validation: list[dict[str, object]]
    train_tuning_cv_folds: "TrainTuningCVFolds"


@dataclass(frozen=True)
class FixedDevelopmentSplits:
    """只含固定 train/validation；用于不需要 CV 的 Dummy 体检。"""

    train: list[dict[str, object]]
    validation: list[dict[str, object]]


@dataclass(frozen=True)
class TrainTuningCVFolds:
    """带来源标识的 train 内 folds，训练器拒绝其他 CV 策略。"""

    rows: list[dict[str, object]]
    purpose: str = "train_tuning_only"


def _read_development(release: DatasetRelease, path: str) -> list[dict[str, object]]:
    assert_split_access(path, stage="training")
    return release.read_csv(path)


def load_development_splits(release: DatasetRelease) -> DevelopmentSplits:
    """默认训练仅取得 train、fixed validation 和 train 内 CV folds。"""

    return DevelopmentSplits(
        train=_read_development(release, TRAIN_PATH),
        validation=_read_development(release, VALIDATION_PATH),
        train_tuning_cv_folds=TrainTuningCVFolds(
            _read_development(release, TUNING_FOLDS_PATH)
        ),
    )


def load_train_validation_splits(release: DatasetRelease) -> FixedDevelopmentSplits:
    """最小 smoke 路径：不读取 train CV，也绝不读取 external。"""

    return FixedDevelopmentSplits(
        train=_read_development(release, TRAIN_PATH),
        validation=_read_development(release, VALIDATION_PATH),
    )


def load_full_development_cv(
    release: DatasetRelease, strategy: Literal["stratified", "scaffold"]
) -> list[dict[str, object]]:
    """用于论文复现/稳健性报告，不能用于此基线的调参或模型选择。"""

    try:
        path = FULL_DEVELOPMENT_CV_PATHS[strategy]
    except KeyError as exc:
        raise ValueError("full development CV strategy 必须是 stratified 或 scaffold") from exc
    assert_split_access(path, stage="training")
    return release.read_csv(path)
