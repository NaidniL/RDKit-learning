"""状态决策表、字段和路径安全测试。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.enums import (  # noqa: E402
    DatasetRole,
    LabelStatus,
    LeakageStatus,
    ReviewStatus,
    SplitEligibility,
    StructureStatus,
)
from modeling_dataset.paths import secure_join, validate_relative_path  # noqa: E402
from modeling_dataset.schema_registry import (  # noqa: E402
    SCHEMA_REGISTRY,
)
from modeling_dataset.serialization import serialize_csv  # noqa: E402
from modeling_dataset.validation import (  # noqa: E402
    RoleState,
    validate_role_state,
    validate_row,
    validate_rows,
)


def role_state(**overrides: object) -> RoleState:
    values: dict[str, object] = {
        "dataset_role": DatasetRole.DEVELOPMENT,
        "label_status": LabelStatus.CLEAR_POSITIVE,
        "role_normalized_label": 1,
        "review_status": ReviewStatus.NOT_REQUIRED,
        "structure_status": StructureStatus.ELIGIBLE,
        "leakage_status": LeakageStatus.NOT_APPLICABLE,
        "has_tautomer_overlap": False,
        "discordant_nonclear_count": 0,
        "has_discordant_nonclear_evidence": False,
        "split_eligibility": SplitEligibility.ELIGIBLE,
    }
    values.update(overrides)
    return RoleState(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "state",
    [
        role_state(),
        role_state(
            structure_status=StructureStatus.INELIGIBLE,
            split_eligibility=SplitEligibility.INELIGIBLE_STRUCTURE,
        ),
        role_state(
            dataset_role=DatasetRole.EXTERNAL,
            leakage_status=LeakageStatus.EXACT_OVERLAP,
            split_eligibility=SplitEligibility.INELIGIBLE_LEAKAGE,
        ),
        role_state(
            label_status=LabelStatus.CONFLICT,
            role_normalized_label=None,
            review_status=ReviewStatus.CONFIRMED_EXCLUDE,
            split_eligibility=SplitEligibility.INELIGIBLE_LABEL,
        ),
    ],
)
def test_valid_state_combinations(state: RoleState) -> None:
    validate_role_state(state, formal=True)


@pytest.mark.parametrize(
    "state",
    [
        role_state(role_normalized_label=0),
        role_state(
            label_status=LabelStatus.UNCERTAIN,
            role_normalized_label=1,
            split_eligibility=SplitEligibility.INELIGIBLE_LABEL,
        ),
        role_state(leakage_status=LeakageStatus.CLEAR),
        role_state(has_tautomer_overlap=True),
        role_state(
            dataset_role=DatasetRole.EXTERNAL,
            leakage_status=LeakageStatus.NOT_APPLICABLE,
        ),
        role_state(split_eligibility=SplitEligibility.INELIGIBLE_LABEL),
    ],
)
def test_invalid_state_combinations_are_rejected(state: RoleState) -> None:
    with pytest.raises(ValueError):
        validate_role_state(state)


def test_pending_conflict_is_allowed_only_for_audit() -> None:
    state = role_state(
        label_status=LabelStatus.CONFLICT,
        role_normalized_label=None,
        review_status=ReviewStatus.PENDING,
        split_eligibility=SplitEligibility.INELIGIBLE_LABEL,
    )
    validate_role_state(state, formal=False)
    with pytest.raises(ValueError, match="不允许 pending"):
        validate_role_state(state, formal=True)


def test_unique_key_and_inchikey_validation() -> None:
    schema = SCHEMA_REGISTRY["modeling/compounds.csv"]
    base = {field.name: None if field.nullable else "x" for field in schema.fields}
    base.update(
        {
            "compound_id": "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
            "standardized_inchikey": "AAAAAAAAAAAAAA-BBBBBBBBBB-C",
            "source_canonical_smiles_json": "[]",
            "parent_smiles_variants_json": "[]",
            "structure_status": "ineligible",
            "structure_reasons_json": '["missing_parent_smiles"]',
            "source_record_keys_json": '["REC:a"]',
        }
    )
    validate_row(base, schema)
    invalid = dict(base, standardized_inchikey="bad")
    with pytest.raises(ValueError, match="InChIKey"):
        validate_row(invalid, schema)
    with pytest.raises(ValueError, match="唯一键重复"):
        validate_rows([base, dict(base)], schema)


def test_invalid_date_source_and_numeric_ranges_are_rejected() -> None:
    review_schema = SCHEMA_REGISTRY["modeling/conflict_reviews.csv"]
    review = {
        "compound_id": "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
        "dataset_role": "development",
        "decision": "confirm_exclude",
        "review_reason": "确认排除",
        "reviewer": "测试",
        "reviewed_at_utc": "2026-99-99T99:99:99Z",
    }
    with pytest.raises(ValueError, match="日期非法"):
        validate_row(review, review_schema)

    exclusion_schema = SCHEMA_REGISTRY["modeling/record_exclusions.csv"]
    exclusion = {
        "record_key": "REC:a",
        "source_dataset": "evil",
        "source_record_id": "00123",
        "exclusion_reason": "x",
    }
    with pytest.raises(ValueError, match="SourceDataset"):
        validate_row(exclusion, exclusion_schema)

    fold_schema = SCHEMA_REGISTRY[
        "splits/full_development_stratified_cv_folds.csv"
    ]
    fold = {
        "compound_id": "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
        "standardized_inchikey": "AAAAAAAAAAAAAA-BBBBBBBBBB-C",
        "normalized_label": 2,
        "fold_id": 5,
    }
    with pytest.raises(ValueError, match="大于最大值"):
        validate_row(fold, fold_schema)


def test_duplicate_class_must_match_counts() -> None:
    schema = SCHEMA_REGISTRY["modeling/duplicate_groups.csv"]
    row = {
        "compound_id": "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
        "dataset_role": "development",
        "record_count": 2,
        "record_keys_json": ["REC:a", "REC:b"],
        "source_labels_json": ["positive"],
        "clear_positive_count": 2,
        "clear_negative_count": 0,
        "nonbinary_count": 0,
        "discordant_nonclear_count": 0,
        "has_discordant_nonclear_evidence": False,
        "exact_duplicate_class": "multiple_nonbinary_only",
    }
    with pytest.raises(ValueError, match="派生结果"):
        serialize_csv([row], schema)


@pytest.mark.parametrize(
    "value",
    ["/absolute/path", "../escape", "a/../b", "a/./b", "a//b", "a/", ""],
)
def test_unsafe_relative_paths_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        validate_relative_path(value)


def test_symlink_in_artifact_or_parent_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "release"
    real = root / "real"
    real.mkdir(parents=True)
    (real / "file.csv").write_text("a\n", encoding="utf-8")
    os.symlink(real, root / "linked")
    with pytest.raises(ValueError, match="符号链接"):
        secure_join(root, "linked/file.csv", must_exist=True)
    os.symlink(real / "file.csv", root / "file-link.csv")
    with pytest.raises(ValueError, match="符号链接"):
        secure_join(root, "file-link.csv", must_exist=True)
