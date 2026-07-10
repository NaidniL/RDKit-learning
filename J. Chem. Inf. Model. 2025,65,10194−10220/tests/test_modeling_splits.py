"""Scheme C split 和确定性 scaffold 五折测试。"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.core_pipeline import validate_core  # noqa: E402
from modeling_dataset.splits import (  # noqa: E402
    build_splits,
    scaffold_folds,
    stratified_folds,
)


def _fold_row(index: int, label: int) -> dict[str, Any]:
    return {
        "compound_id": f"CMP:{index:03d}",
        "standardized_inchikey": f"KEY{index:03d}",
        "normalized_label": label,
    }


def test_stratified_folds_are_order_independent_and_binary() -> None:
    rows = [_fold_row(index, index % 2) for index in range(30)]
    forward = stratified_folds(rows)
    reverse = stratified_folds(list(reversed(rows)))
    assert forward == reverse
    assert {row["fold_id"] for row in forward} == set(range(5))
    for fold_id in range(5):
        assert {
            row["normalized_label"] for row in forward if row["fold_id"] == fold_id
        } == {0, 1}


def test_stratified_folds_reject_too_few_class_members() -> None:
    rows = [_fold_row(index, int(index >= 4)) for index in range(10)]
    with pytest.raises(ValueError, match="正负类样本均不少于 5"):
        stratified_folds(rows)


def test_scaffold_folds_keep_transitive_groups_and_are_deterministic() -> None:
    rows: list[dict[str, Any]] = []
    for group in range(10):
        for label in (0, 1):
            index = group * 2 + label
            rows.append(
                _fold_row(index, label)
                | {
                    "connectivity_key": f"CONN-{group}-{label}",
                    "murcko_scaffold": f"SCAFFOLD-{group}",
                }
            )
    # 不同 scaffold 通过共享 connectivity 再合并，验证连通分量而非单键分组。
    rows[2]["connectivity_key"] = rows[0]["connectivity_key"]
    result = scaffold_folds(rows)
    assert result == scaffold_folds(list(reversed(rows)))
    by_id = {row["compound_id"]: row for row in result}
    assert by_id["CMP:000"]["group_key"] == "CMP:000"
    assert by_id["CMP:002"]["group_key"] == "CMP:000"
    assert by_id["CMP:000"]["fold_id"] == by_id["CMP:002"]["fold_id"]
    for scaffold in {row["murcko_scaffold"] for row in rows}:
        assigned = {
            row["fold_id"] for row in result if row["murcko_scaffold"] == scaffold
        }
        assert len(assigned) == 1


def test_scaffold_folds_reject_missing_connectivity() -> None:
    rows = [
        _fold_row(index, index % 2)
        | {"connectivity_key": f"C{index}", "murcko_scaffold": f"S{index}"}
        for index in range(10)
    ]
    rows[0]["connectivity_key"] = ""
    with pytest.raises(ValueError, match="缺少 connectivity key"):
        scaffold_folds(rows)


def test_full_resolved_split_regression() -> None:
    core = validate_core(ROOT)
    result = build_splits(
        ROOT,
        core.compounds,
        core.finalized_role_resolutions,
        core.leakage,
    )
    assert len(result.train) == 736
    assert len(result.validation) == 185
    assert len(result.train_tuning_folds) == 736
    assert len(result.full_development_stratified_folds) == 921
    assert len(result.full_development_scaffold_folds) == 921
    assert len(result.external_test) == 455
    assert len(result.external_tautomer_sensitivity) == 455
    assert not (
        {row["compound_id"] for row in result.train}
        & {row["compound_id"] for row in result.validation}
    )
    fold_counts: dict[int, Counter[int]] = defaultdict(Counter)
    for row in result.full_development_scaffold_folds:
        fold_counts[row["fold_id"]][row["normalized_label"]] += 1
    assert set(fold_counts) == set(range(5))
    assert all(set(counts) == {0, 1} for counts in fold_counts.values())
