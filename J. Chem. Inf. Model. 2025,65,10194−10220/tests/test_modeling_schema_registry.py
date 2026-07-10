"""阶段 2 schema registry 与枚举回归测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.enums import DatasetRole  # noqa: E402
from modeling_dataset.schema_registry import (  # noqa: E402
    ArtifactClass,
    ArtifactFormat,
    SCHEMA_REGISTRY,
    validate_registry,
)
from modeling_dataset.validation import validate_columns  # noqa: E402


EXPECTED_RELEASE_PATHS = {
    "modeling/records_all.csv",
    "modeling/compounds.csv",
    "modeling/compound_role_resolutions.csv",
    "modeling/conflict_reviews.csv",
    "modeling/compound_exclusions.csv",
    "modeling/record_exclusions.csv",
    "modeling/duplicate_groups.csv",
    "modeling/structure_relation_edges.csv",
    "splits/primary_reproduction/train.csv",
    "splits/primary_reproduction/validation.csv",
    "splits/primary_reproduction/train_tuning_cv_folds.csv",
    "splits/full_development_stratified_cv_folds.csv",
    "splits/full_development_scaffold_cv_folds.csv",
    "splits/external_test.csv",
    "splits/external_test_tautomer_clean_sensitivity.csv",
    "reports/label_conflicts.csv",
    "reports/cross_role_tautomer_overlaps.csv",
    "reports/label_discordant_near_neighbors.csv",
    "reports/nearest_neighbors.csv",
    "reports/split_summary.csv",
    "reports/source_label_crosstab.csv",
    "reports/descriptor_summary.csv",
    "reports/descriptor_failures.csv",
    "reports/evidence_type_crosstab.csv",
    "reports/scaffold_summary.csv",
    "reports/similarity_summary.csv",
    "reports/source_label_association.csv",
    "reports/distribution_shift.csv",
    "reports/development_exact_block_set.csv",
    "reports/development_connectivity_block_set.csv",
    "reports/leakage_audit.json",
    "reports/resolution_summary.json",
}


def test_registry_declares_every_policy_artifact() -> None:
    validate_registry()
    release_paths = {
        path
        for path, schema in SCHEMA_REGISTRY.items()
        if schema.artifact_class is ArtifactClass.RELEASE
    }
    assert release_paths == EXPECTED_RELEASE_PATHS
    candidate = SCHEMA_REGISTRY[
        "reports/modeling_conflict_review_candidates.csv"
    ]
    assert candidate.artifact_class is ArtifactClass.AUDIT_ONLY
    assert candidate.artifact_format is ArtifactFormat.CSV


def test_registry_has_exact_columns_keys_and_sort_keys() -> None:
    for schema in SCHEMA_REGISTRY.values():
        assert schema.path
        if schema.artifact_format is ArtifactFormat.CSV:
            assert schema.columns
            assert len(schema.columns) == len(set(schema.columns))
            assert set(schema.unique_key) <= set(schema.columns)
            assert set(schema.sort_key) <= set(schema.columns)


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "duplicate"])
def test_column_validation_rejects_schema_drift(mode: str) -> None:
    schema = SCHEMA_REGISTRY["modeling/conflict_reviews.csv"]
    columns = list(schema.columns)
    if mode == "missing":
        columns.pop()
    elif mode == "extra":
        columns.append("unexpected")
    elif mode == "reordered":
        columns[0], columns[1] = columns[1], columns[0]
    else:
        columns[-1] = columns[0]
    with pytest.raises(ValueError):
        validate_columns(columns, schema)


def test_unknown_enum_is_rejected() -> None:
    assert DatasetRole.parse("development") is DatasetRole.DEVELOPMENT
    with pytest.raises(ValueError, match="未知的 DatasetRole"):
        DatasetRole.parse("training")
