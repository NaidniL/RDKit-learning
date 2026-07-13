"""模型批次 1 的可序列化、受限实验配置。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .evaluation_guard import assert_no_external_references
from .feature_registry import resolve_feature_specs


ModelName = Literal[
    "dummy", "logistic_regression", "random_forest", "lightgbm", "hist_gradient_boosting"
]
DummyStrategy = Literal["most_frequent", "stratified"]


@dataclass(frozen=True)
class ExperimentConfig:
    model: ModelName
    feature_sets: tuple[str, ...]
    seed: int = 42
    tuning: bool = False
    model_params: dict[str, Any] = field(default_factory=dict)
    threshold: float = 0.5
    dummy_strategy: DummyStrategy = "most_frequent"
    cv_protocol: str = "train_tuning_cv"
    selection_metric: str = "auroc"

    def __post_init__(self) -> None:
        if self.model not in {
            "dummy",
            "logistic_regression",
            "random_forest",
            "lightgbm",
            "hist_gradient_boosting",
        }:
            raise ValueError(f"不支持的 baseline 模型：{self.model}")
        if not isinstance(self.seed, int):
            raise ValueError("seed 必须是整数")
        if not 0 < self.threshold < 1:
            raise ValueError("threshold 必须位于 (0, 1)")
        if self.dummy_strategy not in {"most_frequent", "stratified"}:
            raise ValueError("dummy_strategy 必须是 most_frequent 或 stratified")
        if self.cv_protocol != "train_tuning_cv":
            raise ValueError("模型批次 1 只允许 train_tuning_cv")
        if self.selection_metric != "auroc":
            raise ValueError("模型批次 1 当前只允许 AUROC 作为调参指标")
        resolve_feature_specs(self.feature_sets)
        assert_no_external_references(
            [
                self.model,
                *self.feature_sets,
                json.dumps(self.model_params, sort_keys=True, ensure_ascii=False),
            ]
        )

    def manifest_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["feature_sets"] = list(self.feature_sets)
        result["resolved_model_parameters"] = self.resolved_model_parameters()
        return result

    def resolved_model_parameters(self) -> dict[str, Any]:
        if self.model == "logistic_regression":
            defaults: dict[str, Any] = {
                "penalty": "l2",
                "solver": "liblinear",
                "class_weight": None,
                "max_iter": 5_000,
                "random_state": self.seed,
            }
            defaults.update(self.model_params)
            return defaults
        if self.model == "dummy":
            return {"strategy": self.dummy_strategy, "random_state": self.seed}
        return dict(self.model_params)
