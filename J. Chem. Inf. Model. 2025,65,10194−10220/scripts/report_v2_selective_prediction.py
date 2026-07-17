#!/usr/bin/env python3
"""补齐 v2 的 covered-subset、错误富集与 risk-coverage 开发期诊断。

只从正式 release 加载 train / fixed validation；只写聚合 Markdown 报告，
不保存样本级预测，也不读取任何 external split。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
from scipy.stats import fisher_exact  # noqa: E402

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.experiment_config import ExperimentConfig  # noqa: E402
from modeling.featurizers import featurize_smiles  # noqa: E402
from modeling.metrics import binary_confusion_counts, binary_metrics  # noqa: E402
from modeling.selective_prediction import (  # noqa: E402
    confidence_scores,
    error_pattern_counts,
    hard_predictions,
    model_vote_agreement,
    top_coverage_mask,
    unanimity_mask,
)
from modeling.split_loader import load_train_validation_splits  # noqa: E402
from modeling.train_baseline import build_estimator, predict_probability  # noqa: E402
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


TARGET_COVERAGES = (1.00, 0.95, 0.90, 0.80, 134 / 185, 0.60, 0.50)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs" / "consensus_v2_development_v1.json"
    )
    parser.add_argument(
        "--releases-root", type=Path, default=ROOT / "releases" / "dataset_assembly"
    )
    parser.add_argument(
        "--report", type=Path, default=ROOT / "reports" / "modeling" / "v2_selective_prediction.md"
    )
    return parser.parse_args()


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 不是 canonical JSON object")
    return value


def metric_text(value: float | None) -> str:
    return "null" if value is None else f"{value:.6f}"


def confusion_text(confusion: dict[str, int]) -> str:
    return (
        f"{confusion['true_negative']} / {confusion['false_positive']} / "
        f"{confusion['false_negative']} / {confusion['true_positive']}"
    )


def subset_row(
    *,
    model: str,
    population: str,
    y_true: np.ndarray,
    probability: np.ndarray,
    coverage: float,
    include_ranking_metrics: bool,
) -> str:
    metrics = binary_metrics(y_true, probability, threshold=0.5)
    confusion = binary_confusion_counts(y_true, probability, threshold=0.5)
    auroc = metric_text(metrics["auroc"]) if include_ranking_metrics else "not_defined"
    auprc = metric_text(metrics["auprc"]) if include_ranking_metrics else "not_defined"
    return (
        f"| {model} | {population} | {len(y_true)} | {coverage:.6f} | {auroc} | {auprc} | "
        f"{metrics['mcc']:.6f} | {metrics['accuracy']:.6f} | "
        f"{metric_text(metrics['sensitivity'])} | {metric_text(metrics['specificity'])} | "
        f"{confusion_text(confusion)} |"
    )


def fisher_row(
    *,
    name: str,
    covered_count: int,
    covered_n: int,
    inconclusive_count: int,
    inconclusive_n: int,
) -> str:
    table = [
        [inconclusive_count, inconclusive_n - inconclusive_count],
        [covered_count, covered_n - covered_count],
    ]
    odds_ratio, p_value = fisher_exact(table, alternative="two-sided")
    return (
        f"| {name} | {covered_count} / {covered_n} ({covered_count / covered_n:.6f}) | "
        f"{inconclusive_count} / {inconclusive_n} ({inconclusive_count / inconclusive_n:.6f}) | "
        f"{odds_ratio:.6f} | {p_value:.6f} |"
    )


def main() -> int:
    args = parse_args()
    config = load_canonical_json(args.config)
    if (
        config.get("external_access") != "denied"
        or config.get("threshold") != 0.5
        or config.get("status") != "FROZEN_DEVELOPMENT_ONLY"
    ):
        raise PermissionError("只能使用冻结、external 被拒绝的 v2 development config")
    release = load_formal_release_metadata_without_external_reads(args.releases_root)
    splits = load_train_validation_splits(release)
    y_train = np.asarray([int(row["normalized_label"]) for row in splits.train])
    y_validation = np.asarray([int(row["normalized_label"]) for row in splits.validation])
    probabilities: dict[str, np.ndarray] = {}
    for spec in config["models"]:
        identifier = str(spec["id"])
        feature_sets = tuple(str(item) for item in spec["feature_sets"])
        x_train = featurize_smiles(
            (str(row["canonical_smiles"]) for row in splits.train), feature_sets
        )
        x_validation = featurize_smiles(
            (str(row["canonical_smiles"]) for row in splits.validation), feature_sets
        )
        estimator = build_estimator(
            ExperimentConfig(
                model=str(spec["model"]),
                feature_sets=feature_sets,
                seed=int(config["random_state"]),
                tuning=False,
                model_params=dict(spec["model_params"]),
                threshold=float(config["threshold"]),
            ),
            binary_indices=x_train.binary_indices,
            descriptor_indices=x_train.descriptor_indices,
        ).fit(x_train.values, y_train)
        probabilities[identifier] = predict_probability(estimator, x_validation.values)
    matrix = np.column_stack([probabilities[str(spec["id"])] for spec in config["models"]])
    covered = unanimity_mask(matrix, threshold=0.5)
    inconclusive = ~covered
    hard_calls = hard_predictions(matrix, threshold=0.5)
    consensus_probability = hard_calls[:, 0].astype(float)
    covered_n = int(np.count_nonzero(covered))
    inconclusive_n = int(np.count_nonzero(inconclusive))
    if covered_n != 134 or inconclusive_n != 51:
        raise AssertionError("冻结 unanimity 规则的开发期 coverage 与既有结果不一致")

    lines = [
        "# v2 development-only selective-prediction diagnostics",
        "",
        "状态：`POST HOC, DEVELOPMENT ONLY`。",
        "",
        "本报告使用冻结的三成员 v2 config，在同一 train fit / fixed validation 过程上重现聚合统计。它不读取 external、不写样本级预测、不改变成员、参数、阈值或 unanimity 规则。下面所有风险覆盖策略均为 exploratory 诊断，不能据此事后选择 v2 final rule。",
        "",
        "## Locked inputs",
        "",
        f"- dataset release: `{release.release_id}`",
        f"- dataset manifest SHA-256: `{release.manifest_sha256}`",
        f"- train / validation: `{len(y_train)} / {len(y_validation)}`",
        f"- threshold: `{config['threshold']}`",
        f"- external access: `{config['external_access']}`",
        "",
        "## 1. Fair comparison on the same unanimity-covered subset",
        "",
            "unanimity 覆盖 134/185 个 validation 样本（coverage=0.724324）。consensus 的概率列是 hard call（0/1），因此未定义 AUROC/AUPRC；三个成员的 AUROC/AUPRC 则使用它们各自在同一 134 个样本上的连续概率。",
        "",
        "| Model | Evaluation population | n samples | Coverage of validation | AUROC | AUPRC | MCC | Accuracy | Sensitivity | Specificity | TN / FP / FN / TP |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        subset_row(
            model="unanimity_consensus",
            population="unanimity_covered",
            y_true=y_validation[covered],
            probability=consensus_probability[covered],
            coverage=float(covered.mean()),
            include_ranking_metrics=False,
        ),
    ]
    for identifier, probability in probabilities.items():
        lines.append(
            subset_row(
                model=identifier,
                population="same_unanimity_covered",
                y_true=y_validation[covered],
                probability=probability[covered],
                coverage=float(covered.mean()),
                include_ranking_metrics=True,
            )
        )
    lines.extend(
        [
            "",
            "在 unanimity-covered subset 内，三个成员的 hard call 按定义完全一致，因此它们与 consensus 的 MCC、accuracy、sensitivity、specificity 和混淆计数完全相同。该规则在这里的作用是选择性拒答，不是通过投票修正 covered 样本的成员分类错误。",
        ]
    )

    covered_errors = hard_calls[covered] != y_validation[covered, None]
    inconclusive_errors = hard_calls[inconclusive] != y_validation[inconclusive, None]
    covered_patterns = error_pattern_counts(y_validation[covered], matrix[covered], threshold=0.5)
    inconclusive_patterns = error_pattern_counts(
        y_validation[inconclusive], matrix[inconclusive], threshold=0.5
    )
    lines.extend(
        [
            "",
            "## 2. Error enrichment in inconclusive samples",
            "",
            "错误率以固定 0.5 hard call 计算。Fisher exact test 为两侧、未作多重比较校正的探索性检验；它描述当前 validation 的关联，不能作为 final-policy 选择依据。",
            "",
            "`any_member_wrong` 在 inconclusive 中必为 1，而 `all_members_wrong` 在 inconclusive 中必为 0：这是二元真值与硬预测不一致的逻辑结果，而非独立的错误富集发现。其行按计划完整保留，但应主要解读各成员错误率与 `≥2 members wrong`。",
            "",
            "| Subset | n | LightGBM-descriptors error | RF-MACCS error | RF-ECFP4 error | Any member wrong | ≥2 members wrong | All 3 members wrong |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
            f"| covered | {covered_n} | {covered_errors[:, 0].mean():.6f} | {covered_errors[:, 1].mean():.6f} | {covered_errors[:, 2].mean():.6f} | {covered_patterns['any_member_wrong'] / covered_n:.6f} | {covered_patterns['at_least_two_members_wrong'] / covered_n:.6f} | {covered_patterns['all_members_wrong'] / covered_n:.6f} |",
            f"| inconclusive | {inconclusive_n} | {inconclusive_errors[:, 0].mean():.6f} | {inconclusive_errors[:, 1].mean():.6f} | {inconclusive_errors[:, 2].mean():.6f} | {inconclusive_patterns['any_member_wrong'] / inconclusive_n:.6f} | {inconclusive_patterns['at_least_two_members_wrong'] / inconclusive_n:.6f} | {inconclusive_patterns['all_members_wrong'] / inconclusive_n:.6f} |",
            "",
            "| Error event | Covered error count/rate | Inconclusive error count/rate | Fisher odds ratio (inconclusive vs covered) | Two-sided p value |",
            "|---|---|---|---:|---:|",
        ]
    )
    for index, identifier in enumerate(probabilities):
        lines.append(
            fisher_row(
                name=f"{identifier} wrong",
                covered_count=int(np.count_nonzero(covered_errors[:, index])),
                covered_n=covered_n,
                inconclusive_count=int(np.count_nonzero(inconclusive_errors[:, index])),
                inconclusive_n=inconclusive_n,
            )
        )
    for name in ("any_member_wrong", "at_least_two_members_wrong", "all_members_wrong"):
        lines.append(
            fisher_row(
                name=name,
                covered_count=covered_patterns[name],
                covered_n=covered_n,
                inconclusive_count=inconclusive_patterns[name],
                inconclusive_n=inconclusive_n,
            )
        )

    scores = confidence_scores(matrix, threshold=0.5)
    vote_agreement = model_vote_agreement(matrix, threshold=0.5)
    strategies = {
        "mean_margin": (scores["mean_margin"], None),
        "minimum_margin": (scores["minimum_margin"], None),
        "hard_vote_agreement_then_mean_margin": (vote_agreement, scores["mean_margin"]),
    }
    lines.extend(
        [
            "",
            "## 3. Exploratory risk-coverage curves",
            "",
            "每个策略不使用标签排序：`mean_margin` 为三个概率到 0.5 的平均距离；`minimum_margin` 为最小距离；`hard_vote_agreement_then_mean_margin` 先按 hard-call 多数票一致度（3/3 优于 2/3），再按平均距离。目标 coverage 以 `ceil(target × 185)` 取样；分数并列时按验证集冻结行顺序打破，不输出样本身份。risk = 1 − accuracy。",
            "",
            "| Strategy | Target coverage | Actual n / coverage | Risk | MCC | Accuracy | Sensitivity | Specificity | TN / FP / FN / TP |",
            "|---|---:|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for strategy, (primary, secondary) in strategies.items():
        for target in TARGET_COVERAGES:
            selected = top_coverage_mask(primary, coverage=target, secondary_score=secondary)
            selected_probability = matrix[selected].mean(axis=1)
            metrics = binary_metrics(y_validation[selected], selected_probability, threshold=0.5)
            confusion = binary_confusion_counts(y_validation[selected], selected_probability, threshold=0.5)
            lines.append(
                f"| {strategy} | {target:.6f} | {int(np.count_nonzero(selected))} / {selected.mean():.6f} | "
                f"{1 - metrics['accuracy']:.6f} | {metrics['mcc']:.6f} | {metrics['accuracy']:.6f} | "
                f"{metric_text(metrics['sensitivity'])} | {metric_text(metrics['specificity'])} | {confusion_text(confusion)} |"
            )
    lines.extend(
        [
            "",
            "### Fixed unanimity point",
            "",
            "| Rule | n / coverage | Risk | MCC | Accuracy | Sensitivity | Specificity | TN / FP / FN / TP |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    fixed_metrics = binary_metrics(y_validation[covered], consensus_probability[covered], threshold=0.5)
    fixed_confusion = binary_confusion_counts(
        y_validation[covered], consensus_probability[covered], threshold=0.5
    )
    lines.append(
        f"| fixed_unanimity | {covered_n} / {covered.mean():.6f} | {1 - fixed_metrics['accuracy']:.6f} | "
        f"{fixed_metrics['mcc']:.6f} | {fixed_metrics['accuracy']:.6f} | "
        f"{metric_text(fixed_metrics['sensitivity'])} | {metric_text(fixed_metrics['specificity'])} | {confusion_text(fixed_confusion)} |"
    )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "- 同一 covered subset 的比较才可用于判断 unanimity hard call 与成员 hard call 的相对表现；它不能替代独立 external 证据。",
            "- 当前 covered subset 中成员与 consensus 的 hard-call 表现相同，因此 development 证据支持的定位是“选择性拒答层”，而不是“已证明提升 covered 样本分类性能的集成器”。",
            "- risk-coverage 曲线用于判断固定 unanimity 点是否位于合理区域，不授权根据曲线事后挑选更好看的阈值或规则。",
            "- 任何 v2 final policy 必须在新的 external 访问前另行预注册、冻结并独立审核；v1 primary external 始终不得用于 v2 选择。",
            "",
        ]
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
