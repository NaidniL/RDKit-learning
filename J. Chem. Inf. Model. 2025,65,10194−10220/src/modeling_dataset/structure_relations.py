"""结构同系、互变异构体与 ECFP4 近邻关系审计。"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Any, Iterable, Mapping

from rdkit import DataStructs

from .enums import (
    ComparisonScope,
    DatasetRole,
    LabelRelation,
    LabelStatus,
    RelationType,
)
from .schema_registry import SCHEMA_REGISTRY
from .validation import validate_rows


SIMILARITY_THRESHOLD = 0.85


def _label_relation(label_a: int | None, label_b: int | None) -> LabelRelation:
    if label_a is None or label_b is None:
        return LabelRelation.NOT_COMPARABLE
    if label_a == label_b:
        return LabelRelation.SAME
    return LabelRelation.OPPOSITE


def _role_comparisons(
    compound_a: str,
    compound_b: str,
    roles: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[tuple[ComparisonScope, DatasetRole, DatasetRole]]:
    result: list[tuple[ComparisonScope, DatasetRole, DatasetRole]] = []
    has_a_dev = (compound_a, DatasetRole.DEVELOPMENT.value) in roles
    has_a_ext = (compound_a, DatasetRole.EXTERNAL.value) in roles
    has_b_dev = (compound_b, DatasetRole.DEVELOPMENT.value) in roles
    has_b_ext = (compound_b, DatasetRole.EXTERNAL.value) in roles
    if has_a_dev and has_b_dev:
        result.append(
            (ComparisonScope.DEVELOPMENT, DatasetRole.DEVELOPMENT, DatasetRole.DEVELOPMENT)
        )
    if has_a_ext and has_b_ext:
        result.append(
            (ComparisonScope.EXTERNAL, DatasetRole.EXTERNAL, DatasetRole.EXTERNAL)
        )
    if has_a_dev and has_b_ext:
        result.append(
            (ComparisonScope.CROSS_ROLE, DatasetRole.DEVELOPMENT, DatasetRole.EXTERNAL)
        )
    if has_a_ext and has_b_dev:
        result.append(
            (ComparisonScope.CROSS_ROLE, DatasetRole.EXTERNAL, DatasetRole.DEVELOPMENT)
        )
    return result


def _clear_label(row: Mapping[str, Any]) -> int | None:
    if row["label_status"] not in {
        LabelStatus.CLEAR_POSITIVE.value,
        LabelStatus.CLEAR_NEGATIVE.value,
    }:
        return None
    value = row["role_normalized_label"]
    if value not in {0, 1}:
        raise AssertionError("明确标签角色行缺少二分类标签")
    return int(value)


def build_structure_relation_edges(
    compounds: Iterable[Mapping[str, Any]],
    finalized_roles: Iterable[Mapping[str, Any]],
    fingerprints: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """在结构合格全集中构建所有已登记关系边。"""

    eligible = {
        str(row["compound_id"]): row
        for row in compounds
        if row["structure_status"] == "eligible" and row["parent_smiles"] != ""
    }
    if set(eligible) != set(fingerprints):
        raise ValueError("结构关系比较全集与 ECFP4 指纹集合不一致")
    roles = {
        (str(row["compound_id"]), str(row["dataset_role"])): row
        for row in finalized_roles
    }
    relations: dict[tuple[str, str], set[RelationType]] = defaultdict(set)
    similarities: dict[tuple[str, str], float] = {}

    connectivity_groups: dict[str, list[str]] = defaultdict(list)
    tautomer_groups: dict[str, list[str]] = defaultdict(list)
    for compound_id, row in eligible.items():
        connectivity = str(row["connectivity_key"])
        tautomer = str(row["tautomer_family_key"])
        if connectivity == "":
            raise ValueError(f"结构合格 compound 缺少 connectivity key：{compound_id}")
        connectivity_groups[connectivity].append(compound_id)
        if tautomer != "":
            tautomer_groups[tautomer].append(compound_id)
    for group in connectivity_groups.values():
        for compound_a, compound_b in combinations(sorted(group), 2):
            pair = (compound_a, compound_b)
            relations[pair].add(RelationType.SAME_CONNECTIVITY)
            row_a, row_b = eligible[compound_a], eligible[compound_b]
            if (
                row_a["standardized_inchikey"] != row_b["standardized_inchikey"]
                and row_a["nonisomeric_parent_smiles"] != ""
                and row_a["nonisomeric_parent_smiles"]
                == row_b["nonisomeric_parent_smiles"]
            ):
                relations[pair].add(RelationType.STEREO_VARIANT)
    for group in tautomer_groups.values():
        for compound_a, compound_b in combinations(sorted(group), 2):
            relations[(compound_a, compound_b)].add(RelationType.TAUTOMER_RELATED)

    ordered_ids = sorted(eligible)
    for index, compound_a in enumerate(ordered_ids[:-1]):
        candidate_ids = ordered_ids[index + 1 :]
        scores = DataStructs.BulkTanimotoSimilarity(
            fingerprints[compound_a],
            [fingerprints[compound_id] for compound_id in candidate_ids],
        )
        for compound_b, score in zip(candidate_ids, scores):
            numeric = float(score)
            if numeric >= SIMILARITY_THRESHOLD:
                pair = (compound_a, compound_b)
                relations[pair].add(RelationType.HIGH_SIMILARITY)
                similarities[pair] = numeric

    rows: list[dict[str, Any]] = []
    for (compound_a, compound_b), relation_types in relations.items():
        for scope, role_a, role_b in _role_comparisons(
            compound_a, compound_b, roles
        ):
            role_row_a = roles[(compound_a, role_a.value)]
            role_row_b = roles[(compound_b, role_b.value)]
            label_a = _clear_label(role_row_a)
            label_b = _clear_label(role_row_b)
            label_relation = _label_relation(label_a, label_b)
            for relation_type in relation_types:
                rows.append(
                    {
                        "comparison_scope": scope.value,
                        "compound_id_a": compound_a,
                        "dataset_role_a": role_a.value,
                        "compound_id_b": compound_b,
                        "dataset_role_b": role_b.value,
                        "relation_type": relation_type.value,
                        "similarity": (
                            similarities[(compound_a, compound_b)]
                            if relation_type is RelationType.HIGH_SIMILARITY
                            else None
                        ),
                        "label_a": label_a,
                        "label_b": label_b,
                        "label_relation": label_relation.value,
                    }
                )
    validate_rows(rows, SCHEMA_REGISTRY["modeling/structure_relation_edges.csv"])
    discordant = [
        dict(row)
        for row in rows
        if row["relation_type"] == RelationType.HIGH_SIMILARITY.value
        and row["label_relation"] == LabelRelation.OPPOSITE.value
    ]
    validate_rows(
        discordant,
        SCHEMA_REGISTRY["reports/label_discordant_near_neighbors.csv"],
    )
    return rows, discordant
