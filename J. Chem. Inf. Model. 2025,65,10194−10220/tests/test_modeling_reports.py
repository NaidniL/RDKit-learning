"""阶段 2 最近邻、描述符与分布漂移报告测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.enums import QuerySplit  # noqa: E402
from modeling_dataset.reports import (  # noqa: E402
    DESCRIPTORS,
    _distribution_shift,
    _evidence_type_crosstab,
    _source_reports,
    _summary_values,
    build_reports,
)
from modeling_dataset.structure_algorithms import ecfp4, parse_parent  # noqa: E402


def _member(compound_id: str, label: int) -> dict[str, Any]:
    return {"compound_id": compound_id, "normalized_label": label}


def _compound(compound_id: str, smiles: str, scaffold: str) -> dict[str, Any]:
    return {
        "compound_id": compound_id,
        "parent_smiles": smiles,
        "murcko_scaffold": scaffold,
    }


def _role(
    compound_id: str, role: str, label: int, sources: list[str]
) -> dict[str, Any]:
    return {
        "compound_id": compound_id,
        "dataset_role": role,
        "role_normalized_label": label,
        "label_resolution_sources_json": sources,
    }


def _fixture() -> tuple[
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
]:
    split_rows = {
        "train": [_member("CMP:A", 0), _member("CMP:B", 1)],
        "validation": [_member("CMP:C", 1)],
        "external_test": [_member("CMP:E", 0)],
        "external_tautomer_sensitivity": [_member("CMP:E", 0)],
    }
    compounds = [
        _compound("CMP:A", "c1ccccc1", "c1ccccc1"),
        _compound("CMP:B", "CCO", ""),
        _compound("CMP:C", "Cc1ccccc1", "c1ccccc1"),
        _compound("CMP:E", "C1CCCCC1", "C1CCCCC1"),
    ]
    fingerprints = {
        row["compound_id"]: ecfp4(parse_parent(row["parent_smiles"]))
        for row in compounds
    }
    roles = [
        _role("CMP:A", "development", 0, ["cpdb"]),
        _role("CMP:B", "development", 1, ["cpdb"]),
        _role("CMP:C", "development", 1, ["iris"]),
        _role("CMP:E", "external", 0, ["ccris"]),
    ]
    return split_rows, compounds, fingerprints, roles


def test_build_reports_covers_all_splits_and_registered_statistics() -> None:
    split_rows, compounds, fingerprints, roles = _fixture()
    result = build_reports(split_rows, compounds, fingerprints, roles)

    assert len(result.nearest_neighbors) == 5
    assert {row["query_split"] for row in result.nearest_neighbors} == set(
        split_rows
    )
    train_neighbors = [
        row for row in result.nearest_neighbors if row["query_split"] == "train"
    ]
    assert all(row["query_compound_id"] != row["nearest_compound_id"] for row in train_neighbors)
    assert len(result.descriptor_summary) == 4 * len(DESCRIPTORS)
    assert result.descriptor_failures == []
    molecular_weight = next(
        row
        for row in result.descriptor_summary
        if row["split"] == "train" and row["descriptor"] == "molecular_weight"
    )
    assert molecular_weight["count"] == 2
    assert molecular_weight["missing"] == 0
    validation_scaffold = next(
        row for row in result.scaffold_summary if row["split"] == "validation"
    )
    assert validation_scaffold["compound_weighted_overlap"] == 1.0
    assert validation_scaffold["scaffold_weighted_overlap"] == 1.0
    assert validation_scaffold["singleton_scaffold_rate"] == 1.0
    assert all(row["missing"] == 0 for row in result.similarity_summary)
    assert len(result.distribution_shift) == 3 * len(DESCRIPTORS)


def test_nearest_neighbor_tie_uses_smallest_compound_id(monkeypatch: pytest.MonkeyPatch) -> None:
    split_rows, compounds, fingerprints, roles = _fixture()
    monkeypatch.setattr(
        "modeling_dataset.reports.DataStructs.TanimotoSimilarity",
        lambda _left, _right: 0.5,
    )
    result = build_reports(split_rows, compounds, fingerprints, roles)
    validation = next(
        row for row in result.nearest_neighbors if row["query_split"] == "validation"
    )
    assert validation["nearest_compound_id"] == "CMP:A"


def test_empty_splits_produce_explicit_empty_statuses() -> None:
    split_rows: dict[str, list[dict[str, Any]]] = {
        split.value: [] for split in QuerySplit
    }
    result = build_reports(split_rows, [], {}, [])

    assert result.nearest_neighbors == []
    assert all(row["positive_rate"] is None for row in result.split_summary)
    assert all(row["summary_status"] == "no_observations" for row in result.descriptor_summary)
    assert all(row["status"] == "no_scaffolds" for row in result.scaffold_summary)
    assert all(row["missing"] == 0 for row in result.similarity_summary)
    assert all(row["test_status"] == "insufficient_observations" for row in result.distribution_shift)
    assert all(row["test_status"] == "degenerate_table" for row in result.source_label_association)


def test_population_statistics_and_linear_quantiles_are_fixed() -> None:
    summary = _summary_values([0.0, 10.0], missing=3)
    assert summary["mean"] == 5.0
    assert summary["std"] == 5.0
    assert summary["p05"] == 0.5
    assert summary["p25"] == 2.5
    assert summary["median"] == 5.0
    assert summary["p75"] == 7.5
    assert summary["p95"] == 9.5
    assert summary["missing"] == 3
    singleton = _summary_values([7.0], missing=0)
    assert singleton["std"] == 0.0
    assert all(singleton[key] == 7.0 for key in ("p05", "p25", "median", "p75", "p95"))


def test_query_with_empty_train_has_explicit_missing_neighbor() -> None:
    split_rows: dict[str, list[dict[str, Any]]] = {
        split.value: [] for split in QuerySplit
    }
    split_rows["external_test"] = [_member("CMP:E", 0)]
    split_rows["external_tautomer_sensitivity"] = [_member("CMP:E", 0)]
    compounds = [_compound("CMP:E", "O", "")]
    roles = [_role("CMP:E", "external", 0, ["ccris"])]
    result = build_reports(split_rows, compounds, {}, roles)

    assert len(result.nearest_neighbors) == 2
    assert all(row["nearest_compound_id"] is None for row in result.nearest_neighbors)
    external_similarity = next(
        row for row in result.similarity_summary if row["query_split"] == "external_test"
    )
    assert external_similarity["count"] == 0
    assert external_similarity["missing"] == 1
    assert external_similarity["summary_status"] == "no_observations"
    external_scaffold = next(
        row for row in result.scaffold_summary if row["split"] == "external_test"
    )
    assert external_scaffold["compound_weighted_overlap"] == 0.0
    assert external_scaffold["scaffold_weighted_overlap"] is None
    assert external_scaffold["singleton_scaffold_rate"] is None
    assert external_scaffold["status"] == "no_scaffolds"


def test_evidence_type_composition_uses_resolution_record_keys() -> None:
    splits = {split.value: [] for split in QuerySplit}
    splits["train"] = [_member("CMP:A", 1)]
    roles = {
        ("CMP:A", "development"): {
            "label_resolution_record_keys_json": ["REC:1", "REC:2"]
        }
    }
    records = [
        {"record_key": "REC:1", "evidence_type": "animal_experimental"},
        {
            "record_key": "REC:2",
            "evidence_type": "experimental_unspecified",
        },
    ]
    rows = _evidence_type_crosstab(splits, roles, records)
    assert rows == [
        {
            "split": "train",
            "evidence_type_combination": (
                "animal_experimental|experimental_unspecified"
            ),
            "label": 0,
            "count": 0,
        },
        {
            "split": "train",
            "evidence_type_combination": (
                "animal_experimental|experimental_unspecified"
            ),
            "label": 1,
            "count": 1,
        },
    ]


def test_distribution_shift_handles_zero_variance_and_exact_ks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        split.value: {descriptor: [1.0] for descriptor in DESCRIPTORS}
        for split in QuerySplit
    }
    values["external_test"] = {descriptor: [2.0] for descriptor in DESCRIPTORS}
    calls: list[tuple[str, str]] = []

    def fake_ks(_left: Any, _right: Any, *, alternative: str, method: str) -> Any:
        calls.append((alternative, method))
        return SimpleNamespace(statistic=1.0, pvalue=0.5)

    monkeypatch.setattr("modeling_dataset.reports.stats.ks_2samp", fake_ks)
    result = _distribution_shift(values)
    validation = next(
        row
        for row in result
        if row["comparison_split"] == "validation"
        and row["descriptor"] == "molecular_weight"
    )
    external = next(
        row
        for row in result
        if row["comparison_split"] == "external_test"
        and row["descriptor"] == "molecular_weight"
    )
    assert validation["smd"] == 0.0
    assert validation["smd_status"] == "ok"
    assert external["smd"] is None
    assert external["smd_status"] == "undefined_zero_variance"
    assert calls == [("two-sided", "exact")] * (3 * len(DESCRIPTORS))


def test_descriptor_failure_is_recorded_per_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    split_rows, compounds, fingerprints, roles = _fixture()

    def calculations(_molecule: Any) -> dict[str, Any]:
        result = {descriptor: (lambda: 1.0) for descriptor in DESCRIPTORS}

        def fail() -> float:
            raise ValueError("合成失败")

        result["tpsa"] = fail
        return result

    monkeypatch.setattr("modeling_dataset.reports._descriptor_functions", calculations)
    result = build_reports(split_rows, compounds, fingerprints, roles)
    assert len(result.descriptor_failures) == 5
    assert {row["descriptor"] for row in result.descriptor_failures} == {"tpsa"}
    tpsa_train = next(
        row
        for row in result.descriptor_summary
        if row["split"] == "train" and row["descriptor"] == "tpsa"
    )
    hbd_train = next(
        row
        for row in result.descriptor_summary
        if row["split"] == "train" and row["descriptor"] == "hbd"
    )
    assert (tpsa_train["count"], tpsa_train["missing"]) == (0, 2)
    assert (hbd_train["count"], hbd_train["missing"]) == (2, 0)


def test_source_label_association_reports_confounding_warning() -> None:
    train: list[Mapping[str, Any]] = [
        *[_member(f"CMP:N{index}", 0) for index in range(20)],
        *[_member(f"CMP:P{index}", 1) for index in range(20)],
    ]
    splits: dict[str, list[Mapping[str, Any]]] = {
        split.value: [] for split in QuerySplit
    }
    splits["train"] = train
    roles = {
        (row["compound_id"], "development"): _role(
            row["compound_id"],
            "development",
            row["normalized_label"],
            ["cpdb"] if row["normalized_label"] == 0 else ["iris"],
        )
        for row in train
    }
    crosstab, association, warning = _source_reports(splits, roles)
    train_association = next(row for row in association if row["split"] == "train")
    assert len([row for row in crosstab if row["split"] == "train"]) == 4
    assert train_association["test_status"] == "ok"
    assert train_association["cramers_v"] == 1.0
    assert train_association["source_label_confounding_warning"] is True
    assert warning is True


def test_rejects_incomplete_split_mapping_and_role_label_mismatch() -> None:
    split_rows, compounds, fingerprints, roles = _fixture()
    incomplete = dict(split_rows)
    incomplete.pop("validation")
    with pytest.raises(ValueError, match="划分集合不完整"):
        build_reports(incomplete, compounds, fingerprints, roles)

    bad_roles = [dict(row) for row in roles]
    bad_roles[0]["role_normalized_label"] = 1
    with pytest.raises(ValueError, match="划分标签与角色解析不一致"):
        build_reports(split_rows, compounds, fingerprints, bad_roles)
