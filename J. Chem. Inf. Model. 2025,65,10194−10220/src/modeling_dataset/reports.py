"""构建阶段 2 的最近邻、数据概况与分布漂移报告。"""

from __future__ import annotations

import json
import importlib
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np
from rdkit import DataStructs

from .enums import (
    DatasetRole,
    LabelRelation,
    QuerySplit,
    ScaffoldSummaryStatus,
    SmdStatus,
    SummaryStatus,
    TestStatus,
)
from .schema_registry import SCHEMA_REGISTRY
from .serialization import canonical_json
from .structure_algorithms import parse_parent
from .validation import validate_rows


DESCRIPTORS = (
    "molecular_weight",
    "crippen_logp",
    "tpsa",
    "hbd",
    "hba",
    "rotatable_bonds",
    "ring_count",
    "aromatic_ring_count",
    "heavy_atom_count",
)

SPLIT_ORDER = tuple(item.value for item in QuerySplit)

Crippen = importlib.import_module("rdkit.Chem.Crippen")
Descriptors = importlib.import_module("rdkit.Chem.Descriptors")
rdMolDescriptors = importlib.import_module("rdkit.Chem.rdMolDescriptors")
stats = importlib.import_module("scipy.stats")


@dataclass(frozen=True)
class ReportsBuild:
    nearest_neighbors: list[dict[str, Any]]
    split_summary: list[dict[str, Any]]
    source_label_crosstab: list[dict[str, Any]]
    evidence_type_crosstab: list[dict[str, Any]]
    source_label_association: list[dict[str, Any]]
    descriptor_summary: list[dict[str, Any]]
    descriptor_failures: list[dict[str, Any]]
    scaffold_summary: list[dict[str, Any]]
    similarity_summary: list[dict[str, Any]]
    distribution_shift: list[dict[str, Any]]
    source_label_confounding_warning: bool


def _normalise_splits(
    split_rows: Mapping[str | QuerySplit, Iterable[Mapping[str, Any]]],
) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    for raw_key, rows in split_rows.items():
        key = raw_key.value if isinstance(raw_key, QuerySplit) else str(raw_key)
        QuerySplit.parse(key)
        if key in result:
            raise ValueError(f"划分被重复提供：{key}")
        result[key] = list(rows)
    missing = set(SPLIT_ORDER) - set(result)
    extra = set(result) - set(SPLIT_ORDER)
    if missing or extra:
        raise ValueError(f"划分集合不完整：缺少={sorted(missing)}，额外={sorted(extra)}")
    for split, rows in result.items():
        ids = [str(row["compound_id"]) for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError(f"划分 {split} 包含重复 compound_id")
        for row in rows:
            if row.get("normalized_label") not in {0, 1}:
                raise ValueError(f"划分 {split} 包含非二分类标签")
    sensitivity = {
        str(row["compound_id"])
        for row in result[QuerySplit.EXTERNAL_TAUTOMER_SENSITIVITY.value]
    }
    primary = {
        str(row["compound_id"])
        for row in result[QuerySplit.EXTERNAL_TEST.value]
    }
    if not sensitivity <= primary:
        raise ValueError("tautomer sensitivity external 不是 primary external 的子集")
    return result


def _role_for_split(split: str) -> str:
    if split in {QuerySplit.TRAIN.value, QuerySplit.VALIDATION.value}:
        return DatasetRole.DEVELOPMENT.value
    return DatasetRole.EXTERNAL.value


def _validate_members(
    splits: Mapping[str, list[Mapping[str, Any]]],
    compounds: Mapping[str, Mapping[str, Any]],
    roles: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    for split, rows in splits.items():
        role = _role_for_split(split)
        for row in rows:
            compound_id = str(row["compound_id"])
            if compound_id not in compounds:
                raise ValueError(f"划分成员缺少 compound 行：{compound_id}")
            role_row = roles.get((compound_id, role))
            if role_row is None:
                raise ValueError(f"划分成员缺少角色行：{compound_id}/{role}")
            if role_row["role_normalized_label"] != row["normalized_label"]:
                raise ValueError(f"划分标签与角色解析不一致：{compound_id}/{split}")


def _label_relation(left: int, right: int) -> str:
    return (
        LabelRelation.SAME.value
        if left == right
        else LabelRelation.OPPOSITE.value
    )


def _nearest_neighbors(
    splits: Mapping[str, list[Mapping[str, Any]]],
    fingerprints: Mapping[str, Any],
) -> list[dict[str, Any]]:
    train_rows = {
        str(row["compound_id"]): row for row in splits[QuerySplit.TRAIN.value]
    }
    train_ids = sorted(train_rows)
    result: list[dict[str, Any]] = []
    for split in SPLIT_ORDER:
        for query in sorted(splits[split], key=lambda row: str(row["compound_id"])):
            query_id = str(query["compound_id"])
            candidates = [
                candidate
                for candidate in train_ids
                if candidate != query_id
                and candidate in fingerprints
                and query_id in fingerprints
            ]
            nearest_id: str | None = None
            similarity: float | None = None
            for candidate in candidates:
                score = float(
                    DataStructs.TanimotoSimilarity(
                        fingerprints[query_id], fingerprints[candidate]
                    )
                )
                if not math.isfinite(score):
                    continue
                if similarity is None or score > similarity:
                    similarity = score
                    nearest_id = candidate
            nearest_label = (
                int(train_rows[nearest_id]["normalized_label"])
                if nearest_id is not None
                else None
            )
            query_label = int(query["normalized_label"])
            result.append(
                {
                    "query_compound_id": query_id,
                    "query_split": split,
                    "nearest_compound_id": nearest_id,
                    "nearest_split": (
                        QuerySplit.TRAIN.value if nearest_id is not None else None
                    ),
                    "similarity": similarity,
                    "query_label": query_label,
                    "nearest_label": nearest_label,
                    "label_relation": (
                        _label_relation(query_label, nearest_label)
                        if nearest_label is not None
                        else None
                    ),
                }
            )
    validate_rows(result, SCHEMA_REGISTRY["reports/nearest_neighbors.csv"])
    return result


def _split_summary(
    splits: Mapping[str, list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    result = []
    for split in SPLIT_ORDER:
        labels = [int(row["normalized_label"]) for row in splits[split]]
        positives = sum(labels)
        result.append(
            {
                "split": split,
                "sample_count": len(labels),
                "positive_count": positives,
                "negative_count": len(labels) - positives,
                "positive_rate": positives / len(labels) if labels else None,
            }
        )
    validate_rows(result, SCHEMA_REGISTRY["reports/split_summary.csv"])
    return result


def _source_combination(value: Any) -> str:
    if isinstance(value, str):
        try:
            sources = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("角色来源 JSON 无法解析") from exc
    else:
        sources = value
    if not isinstance(sources, list) or not sources:
        raise ValueError("明确标签角色必须至少有一个解析来源")
    canonical_sources = sorted({str(item) for item in sources})
    if len(canonical_sources) != len(sources):
        raise ValueError("角色解析来源包含重复值")
    return canonical_json(canonical_sources)


def _source_reports(
    splits: Mapping[str, list[Mapping[str, Any]]],
    roles: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    crosstab: list[dict[str, Any]] = []
    associations: list[dict[str, Any]] = []
    any_warning = False
    for split in SPLIT_ORDER:
        role = _role_for_split(split)
        observed: Counter[tuple[str, int]] = Counter()
        for member in splits[split]:
            compound_id = str(member["compound_id"])
            combination = _source_combination(
                roles[(compound_id, role)]["label_resolution_sources_json"]
            )
            observed[(combination, int(member["normalized_label"]))] += 1
        combinations = sorted({key[0] for key in observed})
        for combination in combinations:
            for label in (0, 1):
                crosstab.append(
                    {
                        "split": split,
                        "source_combination": combination,
                        "label": label,
                        "count": observed[(combination, label)],
                    }
                )
        matrix = np.asarray(
            [[observed[(combination, label)] for label in (0, 1)] for combination in combinations],
            dtype=np.int64,
        )
        if matrix.size:
            matrix = matrix[matrix.sum(axis=1) > 0]
            matrix = matrix[:, matrix.sum(axis=0) > 0]
        rows_count = int(matrix.shape[0]) if matrix.ndim == 2 else 0
        columns_count = int(matrix.shape[1]) if matrix.ndim == 2 else 0
        total = int(matrix.sum()) if matrix.size else 0
        purity_warning = any(
            (negative + positive) >= 20
            and max(negative, positive) / (negative + positive) >= 0.90
            for combination in combinations
            for negative, positive in [
                (observed[(combination, 0)], observed[(combination, 1)])
            ]
        )
        if total == 0 or rows_count < 2 or columns_count < 2:
            chi2 = None
            pvalue = None
            cramers_v = 0.0
            status = TestStatus.DEGENERATE_TABLE.value
        else:
            chi2_value, pvalue_value, _, _ = stats.chi2_contingency(
                matrix, correction=False
            )
            chi2 = float(chi2_value)
            pvalue = float(pvalue_value)
            denominator = total * min(rows_count - 1, columns_count - 1)
            cramers_v = (
                min(1.0, math.sqrt(chi2 / denominator)) if denominator else 0.0
            )
            status = TestStatus.OK.value
        warning = purity_warning or cramers_v >= 0.30
        any_warning = any_warning or warning
        associations.append(
            {
                "split": split,
                "chi2_statistic": chi2,
                "chi2_pvalue": pvalue,
                "cramers_v": cramers_v,
                "effective_rows": rows_count,
                "effective_columns": columns_count,
                "test_status": status,
                "source_label_confounding_warning": warning,
            }
        )
    validate_rows(crosstab, SCHEMA_REGISTRY["reports/source_label_crosstab.csv"])
    validate_rows(
        associations, SCHEMA_REGISTRY["reports/source_label_association.csv"]
    )
    return crosstab, associations, any_warning


def _evidence_type_crosstab(
    splits: Mapping[str, list[Mapping[str, Any]]],
    roles: Mapping[tuple[str, str], Mapping[str, Any]],
    records_all: Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """从参与标签解析的来源记录回溯每个样本的证据类型组合。"""

    if records_all is None:
        return []
    record_map = {str(row["record_key"]): row for row in records_all}
    observed: dict[tuple[str, str, int], int] = Counter()
    for split in SPLIT_ORDER:
        role = _role_for_split(split)
        for member in splits[split]:
            compound_id = str(member["compound_id"])
            role_row = roles[(compound_id, role)]
            keys = role_row["label_resolution_record_keys_json"]
            if not isinstance(keys, (list, tuple)) or not keys:
                raise ValueError(f"明确 split 样本缺少标签解析记录：{compound_id}")
            try:
                evidence_types = sorted(
                    {str(record_map[str(key)]["evidence_type"]) for key in keys}
                )
            except KeyError as exc:
                raise ValueError(
                    f"标签解析记录无法回溯 evidence_type：{compound_id}"
                ) from exc
            if not evidence_types or any(value == "" for value in evidence_types):
                raise ValueError(f"样本的 evidence_type 组合为空：{compound_id}")
            combination = "|".join(evidence_types)
            observed[(split, combination, int(member["normalized_label"]))] += 1
    rows: list[dict[str, Any]] = []
    for split in SPLIT_ORDER:
        combinations = sorted(
            {combination for row_split, combination, _ in observed if row_split == split}
        )
        for combination in combinations:
            for label in (0, 1):
                rows.append(
                    {
                        "split": split,
                        "evidence_type_combination": combination,
                        "label": label,
                        "count": observed[(split, combination, label)],
                    }
                )
    validate_rows(rows, SCHEMA_REGISTRY["reports/evidence_type_crosstab.csv"])
    return rows


def _descriptor_functions(molecule: Any) -> dict[str, Any]:
    return {
        "molecular_weight": lambda: Descriptors.MolWt(molecule),
        "crippen_logp": lambda: Crippen.MolLogP(molecule),
        "tpsa": lambda: rdMolDescriptors.CalcTPSA(molecule),
        "hbd": lambda: rdMolDescriptors.CalcNumHBD(molecule),
        "hba": lambda: rdMolDescriptors.CalcNumHBA(molecule),
        "rotatable_bonds": lambda: rdMolDescriptors.CalcNumRotatableBonds(
            molecule, strict=True
        ),
        "ring_count": lambda: rdMolDescriptors.CalcNumRings(molecule),
        "aromatic_ring_count": lambda: rdMolDescriptors.CalcNumAromaticRings(
            molecule
        ),
        "heavy_atom_count": lambda: molecule.GetNumHeavyAtoms(),
    }


def _calculate_descriptors(
    splits: Mapping[str, list[Mapping[str, Any]]],
    compounds: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, list[float]]], list[dict[str, Any]]]:
    values: dict[str, dict[str, list[float]]] = {
        split: {descriptor: [] for descriptor in DESCRIPTORS}
        for split in SPLIT_ORDER
    }
    failures: list[dict[str, Any]] = []
    for split in SPLIT_ORDER:
        for member in splits[split]:
            compound_id = str(member["compound_id"])
            parent_smiles = str(compounds[compound_id]["parent_smiles"])
            try:
                molecule = parse_parent(parent_smiles)
            except Exception:
                for descriptor in DESCRIPTORS:
                    failures.append(
                        {
                            "compound_id": compound_id,
                            "query_split": split,
                            "descriptor": descriptor,
                            "error_reason": "parent_parse_failure",
                        }
                    )
                continue
            for descriptor, calculate in _descriptor_functions(molecule).items():
                try:
                    value = float(calculate())
                    if not math.isfinite(value):
                        raise ValueError("描述符计算产生非有限值")
                except Exception:
                    failures.append(
                        {
                            "compound_id": compound_id,
                            "query_split": split,
                            "descriptor": descriptor,
                            "error_reason": "descriptor_calculation_failure",
                        }
                    )
                    continue
                values[split][descriptor].append(value)
    validate_rows(failures, SCHEMA_REGISTRY["reports/descriptor_failures.csv"])
    return values, failures


def _summary_values(values: list[float], missing: int) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "missing": missing,
            "mean": None,
            "std": None,
            "min": None,
            "p05": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p95": None,
            "max": None,
            "summary_status": SummaryStatus.NO_OBSERVATIONS.value,
        }
    array = np.asarray(values, dtype=np.float64)
    quantiles = np.quantile(array, [0.05, 0.25, 0.50, 0.75, 0.95], method="linear")
    return {
        "count": len(values),
        "missing": missing,
        "mean": float(np.mean(array)),
        "std": float(np.std(array, ddof=0)),
        "min": float(np.min(array)),
        "p05": float(quantiles[0]),
        "p25": float(quantiles[1]),
        "median": float(quantiles[2]),
        "p75": float(quantiles[3]),
        "p95": float(quantiles[4]),
        "max": float(np.max(array)),
        "summary_status": SummaryStatus.OK.value,
    }


def _descriptor_summary(
    splits: Mapping[str, list[Mapping[str, Any]]],
    values: Mapping[str, Mapping[str, list[float]]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for split in SPLIT_ORDER:
        for descriptor in DESCRIPTORS:
            descriptor_values = values[split][descriptor]
            result.append(
                {
                    "split": split,
                    "descriptor": descriptor,
                    **_summary_values(
                        descriptor_values,
                        len(splits[split]) - len(descriptor_values),
                    ),
                }
            )
    validate_rows(result, SCHEMA_REGISTRY["reports/descriptor_summary.csv"])
    return result


def _scaffold_summary(
    splits: Mapping[str, list[Mapping[str, Any]]],
    compounds: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    train_scaffolds = {
        str(compounds[str(row["compound_id"])]["murcko_scaffold"])
        for row in splits[QuerySplit.TRAIN.value]
        if compounds[str(row["compound_id"])]["murcko_scaffold"] != ""
    }
    result: list[dict[str, Any]] = []
    for split in SPLIT_ORDER:
        scaffold_values = [
            str(compounds[str(row["compound_id"])]["murcko_scaffold"])
            for row in splits[split]
        ]
        nonempty = [value for value in scaffold_values if value != ""]
        counts = Counter(nonempty)
        unique_count = len(counts)
        singleton_count = sum(count == 1 for count in counts.values())
        if not scaffold_values:
            compound_overlap = None
            scaffold_overlap = None
            singleton_rate = None
            status = ScaffoldSummaryStatus.NO_SCAFFOLDS.value
        elif unique_count == 0:
            compound_overlap = 0.0
            scaffold_overlap = None
            singleton_rate = None
            status = ScaffoldSummaryStatus.NO_SCAFFOLDS.value
        else:
            compound_overlap = (
                sum(value != "" and value in train_scaffolds for value in scaffold_values)
                / len(scaffold_values)
            )
            scaffold_overlap = len(set(nonempty) & train_scaffolds) / unique_count
            singleton_rate = singleton_count / unique_count
            status = ScaffoldSummaryStatus.OK.value
        result.append(
            {
                "split": split,
                "unique_scaffold_count": unique_count,
                "singleton_scaffold_count": singleton_count,
                "singleton_scaffold_rate": singleton_rate,
                "compound_weighted_overlap": compound_overlap,
                "scaffold_weighted_overlap": scaffold_overlap,
                "status": status,
            }
        )
    validate_rows(result, SCHEMA_REGISTRY["reports/scaffold_summary.csv"])
    return result


def _similarity_summary(
    splits: Mapping[str, list[Mapping[str, Any]]],
    nearest: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_split: dict[str, list[float]] = {split: [] for split in SPLIT_ORDER}
    for row in nearest:
        if row["similarity"] is not None:
            by_split[str(row["query_split"])].append(float(row["similarity"]))
    result: list[dict[str, Any]] = []
    for split in SPLIT_ORDER:
        values = by_split[split]
        missing = len(splits[split]) - len(values)
        if not values:
            result.append(
                {
                    "query_split": split,
                    "count": 0,
                    "missing": missing,
                    "mean": None,
                    "median": None,
                    "p95": None,
                    "max": None,
                    "summary_status": SummaryStatus.NO_OBSERVATIONS.value,
                }
            )
            continue
        array = np.asarray(values, dtype=np.float64)
        result.append(
            {
                "query_split": split,
                "count": len(values),
                "missing": missing,
                "mean": float(np.mean(array)),
                "median": float(np.quantile(array, 0.50, method="linear")),
                "p95": float(np.quantile(array, 0.95, method="linear")),
                "max": float(np.max(array)),
                "summary_status": SummaryStatus.OK.value,
            }
        )
    validate_rows(result, SCHEMA_REGISTRY["reports/similarity_summary.csv"])
    return result


def _distribution_shift(
    values: Mapping[str, Mapping[str, list[float]]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    train = values[QuerySplit.TRAIN.value]
    for split in (
        QuerySplit.VALIDATION.value,
        QuerySplit.EXTERNAL_TEST.value,
        QuerySplit.EXTERNAL_TAUTOMER_SENSITIVITY.value,
    ):
        for descriptor in DESCRIPTORS:
            left = train[descriptor]
            right = values[split][descriptor]
            if not left or not right:
                smd = None
                smd_status = SmdStatus.INSUFFICIENT_OBSERVATIONS.value
                ks_statistic = None
                ks_pvalue = None
                test_status = TestStatus.INSUFFICIENT_OBSERVATIONS.value
            else:
                left_array = np.asarray(left, dtype=np.float64)
                right_array = np.asarray(right, dtype=np.float64)
                left_mean = float(np.mean(left_array))
                right_mean = float(np.mean(right_array))
                pooled = math.sqrt(
                    (float(np.var(left_array, ddof=0)) + float(np.var(right_array, ddof=0)))
                    / 2
                )
                if pooled == 0:
                    if left_mean == right_mean:
                        smd = 0.0
                        smd_status = SmdStatus.OK.value
                    else:
                        smd = None
                        smd_status = SmdStatus.UNDEFINED_ZERO_VARIANCE.value
                else:
                    smd = (right_mean - left_mean) / pooled
                    smd_status = SmdStatus.OK.value
                ks_result = stats.ks_2samp(
                    left_array,
                    right_array,
                    alternative="two-sided",
                    method="exact",
                )
                ks_statistic = float(ks_result.statistic)
                ks_pvalue = float(ks_result.pvalue)
                test_status = TestStatus.OK.value
            result.append(
                {
                    "comparison_split": split,
                    "descriptor": descriptor,
                    "smd": smd,
                    "smd_status": smd_status,
                    "ks_statistic": ks_statistic,
                    "ks_pvalue": ks_pvalue,
                    "test_status": test_status,
                }
            )
    validate_rows(result, SCHEMA_REGISTRY["reports/distribution_shift.csv"])
    return result


def build_reports(
    split_rows: Mapping[str | QuerySplit, Iterable[Mapping[str, Any]]],
    compounds: Iterable[Mapping[str, Any]],
    fingerprints: Mapping[str, Any],
    finalized_roles: Iterable[Mapping[str, Any]],
    records_all: Iterable[Mapping[str, Any]] | None = None,
) -> ReportsBuild:
    """生成全部统计报告行，不写入文件系统。"""

    splits = _normalise_splits(split_rows)
    compound_map = {str(row["compound_id"]): row for row in compounds}
    role_map = {
        (str(row["compound_id"]), str(row["dataset_role"])): row
        for row in finalized_roles
    }
    _validate_members(splits, compound_map, role_map)
    nearest = _nearest_neighbors(splits, fingerprints)
    split_summary = _split_summary(splits)
    crosstab, association, warning = _source_reports(splits, role_map)
    evidence_crosstab = _evidence_type_crosstab(
        splits, role_map, records_all
    )
    descriptor_values, failures = _calculate_descriptors(splits, compound_map)
    descriptor_summary = _descriptor_summary(splits, descriptor_values)
    scaffold_summary = _scaffold_summary(splits, compound_map)
    similarity_summary = _similarity_summary(splits, nearest)
    distribution_shift = _distribution_shift(descriptor_values)
    return ReportsBuild(
        nearest_neighbors=nearest,
        split_summary=split_summary,
        source_label_crosstab=crosstab,
        evidence_type_crosstab=evidence_crosstab,
        source_label_association=association,
        descriptor_summary=descriptor_summary,
        descriptor_failures=failures,
        scaffold_summary=scaffold_summary,
        similarity_summary=similarity_summary,
        distribution_shift=distribution_shift,
        source_label_confounding_warning=warning,
    )
