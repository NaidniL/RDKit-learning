"""训练、调参和模型选择阶段的 external 数据硬隔离。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


EXTERNAL_SPLITS = frozenset(
    {
        "splits/external_test.csv",
        "splits/external_test_tautomer_clean_sensitivity.csv",
    }
)
DEVELOPMENT_SPLITS = frozenset(
    {
        "splits/primary_reproduction/train.csv",
        "splits/primary_reproduction/validation.csv",
        "splits/primary_reproduction/train_tuning_cv_folds.csv",
        "splits/full_development_stratified_cv_folds.csv",
        "splits/full_development_scaffold_cv_folds.csv",
    }
)
TRAINING_STAGES = frozenset(
    {
        "training",
        "hyperparameter_search",
        "feature_selection",
        "threshold_selection",
        "early_stopping",
        "calibration",
        "model_selection",
    }
)


def assert_split_access(split_path: str, *, stage: str) -> None:
    """拒绝在所有模型开发阶段使用 external 或未知 artifact。"""

    if stage not in TRAINING_STAGES | {"external_final"}:
        raise ValueError(f"未知评估阶段：{stage}")
    if split_path not in DEVELOPMENT_SPLITS | EXTERNAL_SPLITS:
        raise PermissionError(f"不允许的模型数据路径：{split_path}")
    if split_path in EXTERNAL_SPLITS and stage != "external_final":
        raise PermissionError(f"{stage} 不得读取 external split")
    if split_path in DEVELOPMENT_SPLITS and stage == "external_final":
        raise PermissionError("external_final 只能读取 external split")


def assert_no_external_references(values: Iterable[str]) -> None:
    """阻止配置、特征或模型选择声明外部数据为输入。"""

    for value in values:
        if "external" in str(value).lower():
            raise PermissionError("模型开发配置不得引用 external")


@dataclass(frozen=True)
class ExternalEvaluationUnlock:
    """未来最终评估的显式闸门；基线训练不会构造此对象。"""

    frozen_experiment_manifest_sha256: str
    approved: bool = False

    def require_approved(self) -> None:
        if not self.approved:
            raise PermissionError("external_final 尚未解锁；需独立审核和冻结模型配置")
