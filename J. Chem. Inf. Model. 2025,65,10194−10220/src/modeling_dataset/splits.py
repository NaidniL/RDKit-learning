"""Scheme C 的确定性划分与五折协议。"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sklearn.model_selection import (  # type: ignore[import-untyped]
    StratifiedKFold,
    train_test_split,
)

from .enums import DatasetRole, SplitEligibility
from .leakage import LeakageBuild
from .schema_registry import SCHEMA_REGISTRY
from .validation import validate_rows


@dataclass(frozen=True)
class SplitBuild:
    """阶段 2 的全部 split 表；所有行均已按标准键排序。"""

    train: list[dict[str, Any]]
    validation: list[dict[str, Any]]
    train_tuning_folds: list[dict[str, Any]]
    full_development_stratified_folds: list[dict[str, Any]]
    full_development_scaffold_folds: list[dict[str, Any]]
    external_test: list[dict[str, Any]]
    external_tautomer_sensitivity: list[dict[str, Any]]


def _read_frozen_rows(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise ValueError(f"冻结 CSV 必须为 UTF-8 无 BOM、LF 换行：{path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames is None:
            raise ValueError(f"冻结 CSV 缺少表头：{path}")
        return [dict(row) for row in reader]


def _frozen_label_map(rows: Iterable[Mapping[str, str]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        key = str(row["standard_inchikey"])
        if key in result:
            raise ValueError(f"冻结 split 的 InChIKey 重复：{key}")
        if row["label_binary"] not in {"0", "1"}:
            raise ValueError(f"冻结 split 标签非法：{key}")
        result[key] = int(row["label_binary"])
    return result


def _split_row(compound: Mapping[str, Any], label: int) -> dict[str, Any]:
    return {
        "compound_id": compound["compound_id"],
        "standardized_inchikey": compound["standardized_inchikey"],
        "canonical_smiles": compound["canonical_smiles"],
        "normalized_label": label,
    }


def _assert_binary_folds(rows: Sequence[Mapping[str, Any]]) -> None:
    fold_labels: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        fold_labels[int(row["fold_id"])].add(int(row["normalized_label"]))
    if set(fold_labels) != set(range(5)):
        raise ValueError("五折划分包含空 fold")
    bad = [fold for fold in range(5) if fold_labels[fold] != {0, 1}]
    if bad:
        raise ValueError(f"五折划分存在单一类别 fold：{bad}")


def stratified_folds(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """按 InChIKey 升序生成固定种子的分层五折表。"""

    ordered = sorted(rows, key=lambda row: str(row["standardized_inchikey"]))
    labels = [int(row["normalized_label"]) for row in ordered]
    counts = Counter(labels)
    if counts[0] < 5 or counts[1] < 5:
        raise ValueError(
            "分层五折要求正负类样本均不少于 5；"
            f"当前负类={counts[0]}，正类={counts[1]}"
        )
    splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    fold_by_index: dict[int, int] = {}
    for fold_id, (_, test_indices) in enumerate(splitter.split(ordered, labels)):
        for index in test_indices:
            fold_by_index[int(index)] = fold_id
    result = [
        {
            "compound_id": row["compound_id"],
            "standardized_inchikey": row["standardized_inchikey"],
            "normalized_label": int(row["normalized_label"]),
            "fold_id": fold_by_index[index],
        }
        for index, row in enumerate(ordered)
    ]
    _assert_binary_folds(result)
    return result


class _DisjointSet:
    def __init__(self, members: Iterable[str]) -> None:
        self.parent = {member: member for member in members}

    def find(self, member: str) -> str:
        parent = self.parent[member]
        if parent != member:
            self.parent[member] = self.find(parent)
        return self.parent[member]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        # 固定父节点，避免输入顺序影响连通分量。
        low, high = sorted((left_root, right_root))
        self.parent[high] = low


def _scaffold_groups(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    ids = [str(row["compound_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("scaffold CV 输入 compound_id 重复")
    disjoint = _DisjointSet(ids)
    by_scaffold: dict[str, list[str]] = defaultdict(list)
    by_connectivity: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        compound_id = str(row["compound_id"])
        connectivity = str(row["connectivity_key"])
        if connectivity == "":
            raise ValueError(f"eligible compound 缺少 connectivity key：{compound_id}")
        scaffold = str(row["murcko_scaffold"])
        if scaffold != "":
            by_scaffold[scaffold].append(compound_id)
        by_connectivity[connectivity].append(compound_id)
    for members in (*by_scaffold.values(), *by_connectivity.values()):
        anchor = min(members)
        for member in members:
            disjoint.union(anchor, member)
    components: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        components[disjoint.find(str(row["compound_id"]))].append(row)
    result: dict[str, list[Mapping[str, Any]]] = {}
    for component_members in components.values():
        group_key = min(str(row["compound_id"]) for row in component_members)
        result[group_key] = component_members
    return result


def _allocation_score(
    fold_counts: Sequence[tuple[int, int, int]],
    *,
    total: int,
    positive: int,
    negative: int,
) -> Fraction:
    score = Fraction(0)
    for count, positive_count, negative_count in fold_counts:
        score += ((Fraction(count) - Fraction(total, 5)) / total) ** 2
        score += ((Fraction(positive_count) - Fraction(positive, 5)) / positive) ** 2
        score += ((Fraction(negative_count) - Fraction(negative, 5)) / negative) ** 2
    return score


def scaffold_folds(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """按 scaffold/connectivity 连通分量确定性分配五折。"""

    ordered = sorted(rows, key=lambda row: str(row["standardized_inchikey"]))
    labels = Counter(int(row["normalized_label"]) for row in ordered)
    total = len(ordered)
    positive = labels[1]
    negative = labels[0]
    if total == 0 or positive == 0 or negative == 0:
        raise ValueError("scaffold 五折要求输入非空且同时包含正负类")
    groups = _scaffold_groups(ordered)
    group_order = sorted(
        groups,
        key=lambda key: (
            -len(groups[key]),
            -sum(int(row["normalized_label"]) for row in groups[key]),
            key,
        ),
    )
    counts = [(0, 0, 0) for _ in range(5)]
    fold_by_group: dict[str, int] = {}
    for group_key in group_order:
        members = groups[group_key]
        group_total = len(members)
        group_positive = sum(int(row["normalized_label"]) for row in members)
        group_negative = group_total - group_positive
        candidates: list[tuple[Fraction, int]] = []
        for fold_id in range(5):
            proposed = list(counts)
            old = proposed[fold_id]
            proposed[fold_id] = (
                old[0] + group_total,
                old[1] + group_positive,
                old[2] + group_negative,
            )
            candidates.append(
                (
                    _allocation_score(
                        proposed,
                        total=total,
                        positive=positive,
                        negative=negative,
                    ),
                    fold_id,
                )
            )
        _, selected = min(candidates)
        old = counts[selected]
        counts[selected] = (
            old[0] + group_total,
            old[1] + group_positive,
            old[2] + group_negative,
        )
        fold_by_group[group_key] = selected
    group_by_id = {
        str(row["compound_id"]): group_key
        for group_key, members in groups.items()
        for row in members
    }
    result = [
        {
            "compound_id": row["compound_id"],
            "standardized_inchikey": row["standardized_inchikey"],
            "normalized_label": int(row["normalized_label"]),
            "murcko_scaffold": row["murcko_scaffold"],
            "group_key": group_by_id[str(row["compound_id"])],
            "fold_id": fold_by_group[group_by_id[str(row["compound_id"])]],
        }
        for row in ordered
    ]
    _assert_binary_folds(result)
    return result


def _role_labels(
    finalized_roles: Iterable[Mapping[str, Any]], role: DatasetRole
) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in finalized_roles:
        if row["dataset_role"] != role.value:
            continue
        if row["split_eligibility"] != SplitEligibility.ELIGIBLE.value:
            continue
        label = row["role_normalized_label"]
        if label in {0, 1}:
            result[str(row["compound_id"])] = int(label)
    return result


def build_splits(
    root: Path,
    compounds: Iterable[Mapping[str, Any]],
    finalized_roles: Iterable[Mapping[str, Any]],
    leakage: LeakageBuild,
) -> SplitBuild:
    """复现冻结 holdout，并生成三套 CV 与两套 external 表。"""

    compound_map = {str(row["compound_id"]): row for row in compounds}
    role_rows = list(finalized_roles)
    development_labels = _role_labels(role_rows, DatasetRole.DEVELOPMENT)
    external_labels = _role_labels(role_rows, DatasetRole.EXTERNAL)
    processed = root / "data" / "processed"
    development_frozen = _read_frozen_rows(processed / "development_pool.csv")
    inchikeys = [row["standard_inchikey"] for row in development_frozen]
    if inchikeys != sorted(inchikeys) or len(inchikeys) != len(set(inchikeys)):
        raise ValueError("development_pool.csv 未按 InChIKey 升序或包含重复")
    development_map = _frozen_label_map(development_frozen)
    # 阶段 1 的明确标签是不可变子集；第 4 节批准的多数计数标签可在此基础上增加。
    for inchikey, label in development_map.items():
        compound_id = f"CMP:{inchikey}"
        compound = compound_map.get(compound_id)
        if compound is None or development_labels.get(compound_id) != label:
            raise ValueError(f"development 成员或标签无法重建：{compound_id}")
        if compound["structure_status"] != "eligible":
            raise ValueError(f"development 成员结构不合格：{compound_id}")
    development_rows = [
        _split_row(compound_map[compound_id], label)
        for compound_id, label in sorted(development_labels.items())
    ]
    scaffold_inputs = [
        row
        | {
            "connectivity_key": compound_map[str(row["compound_id"])][
                "connectivity_key"
            ],
            "murcko_scaffold": compound_map[str(row["compound_id"])][
                "murcko_scaffold"
            ],
        }
        for row in development_rows
    ]

    generated_train, generated_validation = train_test_split(
        development_rows,
        test_size=0.20,
        random_state=42,
        stratify=[row["normalized_label"] for row in development_rows],
        shuffle=True,
    )
    train = sorted(generated_train, key=lambda row: row["standardized_inchikey"])
    validation = sorted(
        generated_validation, key=lambda row: row["standardized_inchikey"]
    )

    primary_rows: list[dict[str, Any]] = []
    for compound_id in sorted(leakage.primary_external_ids):
        compound = compound_map[compound_id]
        external_label = external_labels.get(compound_id)
        if external_label is None:
            raise ValueError(f"primary external 缺少明确标签：{compound_id}")
        primary_rows.append(_split_row(compound, external_label))
    primary_rows.sort(key=lambda row: row["standardized_inchikey"])
    frozen_external = _frozen_label_map(
        _read_frozen_rows(processed / "external_ccris_test.csv")
    )
    primary_map = {
        str(row["standardized_inchikey"]): int(row["normalized_label"])
        for row in primary_rows
    }
    if not frozen_external.items() <= primary_map.items():
        raise ValueError("primary external 未完整保留阶段 1 冻结成员或标签")
    sensitivity = [
        row
        for row in primary_rows
        if str(row["compound_id"]) in leakage.sensitivity_external_ids
    ]

    train_ids = {str(row["compound_id"]) for row in train}
    validation_ids = {str(row["compound_id"]) for row in validation}
    external_ids = {str(row["compound_id"]) for row in primary_rows}
    if (
        train_ids & validation_ids
        or train_ids & external_ids
        or validation_ids & external_ids
    ):
        raise ValueError("train/validation/primary external 存在完全结构交集")

    train_tuning = stratified_folds(train)
    full_stratified = stratified_folds(development_rows)
    scaffold = scaffold_folds(scaffold_inputs)
    artifact_rows = (
        (train, "splits/primary_reproduction/train.csv"),
        (validation, "splits/primary_reproduction/validation.csv"),
        (
            train_tuning,
            "splits/primary_reproduction/train_tuning_cv_folds.csv",
        ),
        (
            full_stratified,
            "splits/full_development_stratified_cv_folds.csv",
        ),
        (scaffold, "splits/full_development_scaffold_cv_folds.csv"),
        (primary_rows, "splits/external_test.csv"),
        (
            sensitivity,
            "splits/external_test_tautomer_clean_sensitivity.csv",
        ),
    )
    for rows, schema_path in artifact_rows:
        validate_rows(rows, SCHEMA_REGISTRY[schema_path])
    return SplitBuild(
        train=train,
        validation=validation,
        train_tuning_folds=train_tuning,
        full_development_stratified_folds=full_stratified,
        full_development_scaffold_folds=scaffold,
        external_test=primary_rows,
        external_tautomer_sensitivity=sensitivity,
    )
