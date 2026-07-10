"""版本化 artifact schema 注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .enums import ENUM_RANKS, ENUM_TYPES


SCHEMA_VERSION = "1.0.0"


class FieldType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"
    UTC_TIME = "utc_time"
    INCHIKEY = "inchikey"


class ArtifactClass(str, Enum):
    RELEASE = "release_artifact"
    AUDIT_ONLY = "audit_only_artifact"


class ArtifactFormat(str, Enum):
    CSV = "csv"
    JSON = "json"


@dataclass(frozen=True)
class FieldSpec:
    """单个字段的固定类型与可空规则。"""

    name: str
    field_type: FieldType = FieldType.STRING
    nullable: bool = False
    enum_name: str | None = None
    canonical_array: bool = False
    numeric_min: float | None = None
    numeric_max: float | None = None


@dataclass(frozen=True)
class ArtifactSchema:
    """单个确定性 artifact 的完整 schema。"""

    path: str
    artifact_class: ArtifactClass
    artifact_format: ArtifactFormat
    fields: tuple[FieldSpec, ...] = ()
    unique_key: tuple[str, ...] = ()
    sort_key: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)


def field(
    name: str,
    field_type: FieldType = FieldType.STRING,
    *,
    nullable: bool = False,
    enum_name: str | None = None,
    canonical_array: bool = False,
    numeric_min: float | None = None,
    numeric_max: float | None = None,
) -> FieldSpec:
    return FieldSpec(
        name,
        field_type,
        nullable,
        enum_name,
        canonical_array,
        numeric_min,
        numeric_max,
    )


def strings(names: Iterable[str], *, nullable: bool = True) -> tuple[FieldSpec, ...]:
    return tuple(field(name, nullable=nullable) for name in names)


SOURCE_RECORD_COLUMNS = (
    "source",
    "dataset_role",
    "source_record_id",
    "source_chemical_id",
    "casrn",
    "name",
    "endpoint",
    "species",
    "route",
    "reference",
    "label_raw",
    "label_category",
    "label_candidate",
    "label_confidence",
    "label_reason",
    "source_payload_json",
    "structure_source_record_id",
    "structure_source_status",
    "structure_source_error",
    "structure_provenance",
    "pubchem_sid",
    "pubchem_cid",
    "source_dtxsid",
    "source_connectivity_smiles",
    "source_pubchem_inchikey",
    "raw_smiles",
    "canonical_smiles",
    "parent_smiles",
    "standard_inchikey",
    "connectivity_key",
    "murcko_scaffold",
    "rdkit_parse_ok",
    "rdkit_mol_ok",
    "leakage_connectivity_keys_json",
    "structure_category",
    "standardization_notes",
    "formal_charge_before",
    "formal_charge_after",
    "uncharging_applied",
    "residual_charge",
    "tautomer_standardized",
    "inorganic_carbon_review_required",
    "manual_review_decision",
    "manual_review_reason",
    "manual_reviewer",
    "model_structure_ok",
    "exclusion_reason",
)


def csv_schema(
    path: str,
    fields: tuple[FieldSpec, ...],
    unique_key: tuple[str, ...],
    sort_key: tuple[str, ...],
    *,
    artifact_class: ArtifactClass = ArtifactClass.RELEASE,
) -> ArtifactSchema:
    return ArtifactSchema(
        path=path,
        artifact_class=artifact_class,
        artifact_format=ArtifactFormat.CSV,
        fields=fields,
        unique_key=unique_key,
        sort_key=sort_key,
    )


def json_schema(path: str, fields: tuple[FieldSpec, ...]) -> ArtifactSchema:
    return ArtifactSchema(
        path=path,
        artifact_class=ArtifactClass.RELEASE,
        artifact_format=ArtifactFormat.JSON,
        fields=fields,
    )


SOURCE_FIELD_OVERRIDES: dict[str, FieldSpec] = {
    "source": field("source", enum_name="SourceDataset"),
    "dataset_role": field("dataset_role", enum_name="DatasetRole"),
    "source_record_id": field("source_record_id"),
    "source_payload_json": field("source_payload_json", FieldType.JSON),
    "standard_inchikey": field(
        "standard_inchikey", FieldType.INCHIKEY, nullable=True
    ),
    "rdkit_parse_ok": field("rdkit_parse_ok", FieldType.BOOLEAN),
    "rdkit_mol_ok": field("rdkit_mol_ok", FieldType.BOOLEAN),
    "leakage_connectivity_keys_json": field(
        "leakage_connectivity_keys_json",
        FieldType.JSON,
        canonical_array=True,
    ),
    "uncharging_applied": field("uncharging_applied", FieldType.BOOLEAN),
    "formal_charge_before": field(
        "formal_charge_before", FieldType.INTEGER, nullable=True
    ),
    "formal_charge_after": field(
        "formal_charge_after", FieldType.INTEGER, nullable=True
    ),
    "residual_charge": field("residual_charge", FieldType.BOOLEAN),
    "tautomer_standardized": field("tautomer_standardized", FieldType.BOOLEAN),
    "inorganic_carbon_review_required": field(
        "inorganic_carbon_review_required", FieldType.BOOLEAN
    ),
    "model_structure_ok": field("model_structure_ok", FieldType.BOOLEAN),
}


RECORDS_ALL_FIELDS = (
    tuple(
        SOURCE_FIELD_OVERRIDES.get(name, field(name, nullable=True))
        for name in SOURCE_RECORD_COLUMNS
    )
    + (
        field("record_key"),
        field("source_dataset", enum_name="SourceDataset"),
        field("source_label", nullable=True),
        field(
            "normalized_label",
            FieldType.INTEGER,
            nullable=True,
            numeric_min=0,
            numeric_max=1,
        ),
        field("label_rule", enum_name="LabelRule"),
        field("evidence_type", enum_name="EvidenceType"),
        field("cleaning_run_id"),
    )
)


COMPOUND_FIELDS = (
    field("compound_id"),
    field("standardized_inchikey", FieldType.INCHIKEY),
    field("connectivity_key"),
    field("canonical_smiles", nullable=True),
    field("parent_smiles", nullable=True),
    field("source_canonical_smiles_json", FieldType.JSON, canonical_array=True),
    field("parent_smiles_variants_json", FieldType.JSON, canonical_array=True),
    field("nonisomeric_parent_smiles", nullable=True),
    field("tautomer_family_key", nullable=True),
    field("murcko_scaffold", nullable=True),
    field("structure_status", enum_name="StructureStatus"),
    field("structure_reasons_json", FieldType.JSON, canonical_array=True),
    field("source_record_keys_json", FieldType.JSON, canonical_array=True),
    field("cleaning_run_id"),
)


ROLE_RESOLUTION_FIELDS = (
    field("compound_id"),
    field("dataset_role", enum_name="DatasetRole"),
    field(
        "role_normalized_label",
        FieldType.INTEGER,
        nullable=True,
        numeric_min=0,
        numeric_max=1,
    ),
    field("label_status", enum_name="LabelStatus"),
    field("review_status", enum_name="ReviewStatus"),
    field("label_resolution_record_keys_json", FieldType.JSON, canonical_array=True),
    field("nonresolution_record_keys_json", FieldType.JSON, canonical_array=True),
    field("label_resolution_sources_json", FieldType.JSON, canonical_array=True),
    field("discordant_nonclear_count", FieldType.INTEGER, numeric_min=0),
    field("has_discordant_nonclear_evidence", FieldType.BOOLEAN),
    field("structure_status", enum_name="StructureStatus"),
    field("leakage_status", enum_name="LeakageStatus"),
    field("has_tautomer_overlap", FieldType.BOOLEAN),
    field("split_eligibility", enum_name="SplitEligibility"),
    field("exclusion_reasons_json", FieldType.JSON, canonical_array=True),
    field("resolution_rules_json", FieldType.JSON, canonical_array=True),
    field("cleaning_run_id"),
)


CONFLICT_REVIEW_FIELDS = (
    field("compound_id"),
    field("dataset_role", enum_name="DatasetRole"),
    field("clear_positive_count", FieldType.INTEGER, numeric_min=0),
    field("clear_negative_count", FieldType.INTEGER, numeric_min=0),
    field("decision", enum_name="ReviewDecision"),
    field("resolved_label", FieldType.INTEGER, nullable=True, numeric_min=0, numeric_max=1),
    field("resolution_reason"),
)


COMPOUND_EXCLUSION_FIELDS = (
    field("compound_id"),
    field("dataset_role", enum_name="DatasetRole"),
    field("exclusion_reason"),
)


RECORD_EXCLUSION_FIELDS = (
    field("record_key"),
    field("source_dataset", enum_name="SourceDataset"),
    field("source_record_id"),
    field("exclusion_reason"),
)


DUPLICATE_GROUP_FIELDS = (
    field("compound_id"),
    field("dataset_role", enum_name="DatasetRole"),
    field("record_count", FieldType.INTEGER, numeric_min=1),
    field("record_keys_json", FieldType.JSON, canonical_array=True),
    field("source_labels_json", FieldType.JSON, canonical_array=True),
    field("clear_positive_count", FieldType.INTEGER, numeric_min=0),
    field("clear_negative_count", FieldType.INTEGER, numeric_min=0),
    field("nonbinary_count", FieldType.INTEGER, numeric_min=0),
    field("discordant_nonclear_count", FieldType.INTEGER, numeric_min=0),
    field("has_discordant_nonclear_evidence", FieldType.BOOLEAN),
    field("exact_duplicate_class", enum_name="ExactDuplicateClass"),
)


RELATION_EDGE_FIELDS = (
    field("comparison_scope", enum_name="ComparisonScope"),
    field("compound_id_a"),
    field("dataset_role_a", enum_name="DatasetRole"),
    field("compound_id_b"),
    field("dataset_role_b", enum_name="DatasetRole"),
    field("relation_type", enum_name="RelationType"),
    field(
        "similarity", FieldType.FLOAT, nullable=True, numeric_min=0, numeric_max=1
    ),
    field(
        "label_a", FieldType.INTEGER, nullable=True, numeric_min=0, numeric_max=1
    ),
    field(
        "label_b", FieldType.INTEGER, nullable=True, numeric_min=0, numeric_max=1
    ),
    field("label_relation", enum_name="LabelRelation"),
)


SPLIT_FIELDS = (
    field("compound_id"),
    field("standardized_inchikey", FieldType.INCHIKEY),
    field("canonical_smiles"),
    field("normalized_label", FieldType.INTEGER, numeric_min=0, numeric_max=1),
)


FOLD_FIELDS = (
    field("compound_id"),
    field("standardized_inchikey", FieldType.INCHIKEY),
    field("normalized_label", FieldType.INTEGER, numeric_min=0, numeric_max=1),
    field("fold_id", FieldType.INTEGER, numeric_min=0, numeric_max=4),
)


SCAFFOLD_FOLD_FIELDS = FOLD_FIELDS[:-1] + (
    field("murcko_scaffold", nullable=True),
    field("group_key"),
    field("fold_id", FieldType.INTEGER, numeric_min=0, numeric_max=4),
)


NEAREST_NEIGHBOR_FIELDS = (
    field("query_compound_id"),
    field("query_split", enum_name="QuerySplit"),
    field("nearest_compound_id", nullable=True),
    field("nearest_split", enum_name="QuerySplit", nullable=True),
    field(
        "similarity", FieldType.FLOAT, nullable=True, numeric_min=0, numeric_max=1
    ),
    field("query_label", FieldType.INTEGER, numeric_min=0, numeric_max=1),
    field(
        "nearest_label",
        FieldType.INTEGER,
        nullable=True,
        numeric_min=0,
        numeric_max=1,
    ),
    field("label_relation", enum_name="LabelRelation", nullable=True),
)


ARTIFACT_SCHEMAS: tuple[ArtifactSchema, ...] = (
    csv_schema(
        "modeling/records_all.csv",
        RECORDS_ALL_FIELDS,
        ("record_key",),
        ("source_dataset", "source_record_id", "record_key"),
    ),
    csv_schema(
        "modeling/compounds.csv",
        COMPOUND_FIELDS,
        ("compound_id",),
        ("standardized_inchikey",),
    ),
    csv_schema(
        "modeling/compound_role_resolutions.csv",
        ROLE_RESOLUTION_FIELDS,
        ("compound_id", "dataset_role"),
        ("compound_id", "dataset_role"),
    ),
    csv_schema(
        "modeling/conflict_reviews.csv",
        CONFLICT_REVIEW_FIELDS,
        ("compound_id", "dataset_role"),
        ("compound_id", "dataset_role"),
    ),
    csv_schema(
        "modeling/compound_exclusions.csv",
        COMPOUND_EXCLUSION_FIELDS,
        ("compound_id", "dataset_role", "exclusion_reason"),
        ("compound_id", "dataset_role", "exclusion_reason"),
    ),
    csv_schema(
        "modeling/record_exclusions.csv",
        RECORD_EXCLUSION_FIELDS,
        ("record_key", "exclusion_reason"),
        ("source_dataset", "source_record_id", "exclusion_reason"),
    ),
    csv_schema(
        "modeling/duplicate_groups.csv",
        DUPLICATE_GROUP_FIELDS,
        ("compound_id", "dataset_role"),
        ("compound_id", "dataset_role"),
    ),
    csv_schema(
        "modeling/structure_relation_edges.csv",
        RELATION_EDGE_FIELDS,
        (
            "comparison_scope",
            "compound_id_a",
            "dataset_role_a",
            "compound_id_b",
            "dataset_role_b",
            "relation_type",
        ),
        (
            "comparison_scope",
            "compound_id_a",
            "dataset_role_a",
            "compound_id_b",
            "dataset_role_b",
            "relation_type",
        ),
    ),
    csv_schema(
        "splits/primary_reproduction/train.csv",
        SPLIT_FIELDS,
        ("compound_id",),
        ("standardized_inchikey",),
    ),
    csv_schema(
        "splits/primary_reproduction/validation.csv",
        SPLIT_FIELDS,
        ("compound_id",),
        ("standardized_inchikey",),
    ),
    csv_schema(
        "splits/primary_reproduction/train_tuning_cv_folds.csv",
        FOLD_FIELDS,
        ("compound_id",),
        ("standardized_inchikey",),
    ),
    csv_schema(
        "splits/full_development_stratified_cv_folds.csv",
        FOLD_FIELDS,
        ("compound_id",),
        ("standardized_inchikey",),
    ),
    csv_schema(
        "splits/full_development_scaffold_cv_folds.csv",
        SCAFFOLD_FOLD_FIELDS,
        ("compound_id",),
        ("standardized_inchikey",),
    ),
    csv_schema(
        "splits/external_test.csv",
        SPLIT_FIELDS,
        ("compound_id",),
        ("standardized_inchikey",),
    ),
    csv_schema(
        "splits/external_test_tautomer_clean_sensitivity.csv",
        SPLIT_FIELDS,
        ("compound_id",),
        ("standardized_inchikey",),
    ),
    csv_schema(
        "reports/label_conflicts.csv",
        (
            field("compound_id"),
            field("dataset_role", enum_name="DatasetRole"),
            field("clear_positive_count", FieldType.INTEGER, numeric_min=0),
            field("clear_negative_count", FieldType.INTEGER, numeric_min=0),
            field("decision", enum_name="ReviewDecision"),
            field("resolved_label", FieldType.INTEGER, nullable=True, numeric_min=0, numeric_max=1),
            field("resolution_reason"),
        ),
        ("compound_id", "dataset_role"),
        ("compound_id", "dataset_role"),
    ),
    csv_schema(
        "reports/cross_role_tautomer_overlaps.csv",
        (
            field("external_compound_id"),
            field("tautomer_family_key"),
            field(
                "development_compound_ids_json",
                FieldType.JSON,
                canonical_array=True,
            ),
            field("in_primary_external", FieldType.BOOLEAN),
            field("removed_from_tautomer_sensitivity", FieldType.BOOLEAN),
        ),
        ("external_compound_id",),
        ("external_compound_id",),
    ),
    csv_schema(
        "reports/label_discordant_near_neighbors.csv",
        RELATION_EDGE_FIELDS,
        (
            "comparison_scope",
            "compound_id_a",
            "dataset_role_a",
            "compound_id_b",
            "dataset_role_b",
            "relation_type",
        ),
        (
            "comparison_scope",
            "compound_id_a",
            "dataset_role_a",
            "compound_id_b",
            "dataset_role_b",
            "relation_type",
        ),
    ),
    csv_schema(
        "reports/nearest_neighbors.csv",
        NEAREST_NEIGHBOR_FIELDS,
        ("query_compound_id", "query_split"),
        (
            "query_split",
            "query_compound_id",
            "nearest_split",
            "nearest_compound_id",
        ),
    ),
    csv_schema(
        "reports/split_summary.csv",
        (
            field("split", enum_name="QuerySplit"),
            field("sample_count", FieldType.INTEGER, numeric_min=0),
            field("positive_count", FieldType.INTEGER, numeric_min=0),
            field("negative_count", FieldType.INTEGER, numeric_min=0),
            field(
                "positive_rate",
                FieldType.FLOAT,
                nullable=True,
                numeric_min=0,
                numeric_max=1,
            ),
        ),
        ("split",),
        ("split",),
    ),
    csv_schema(
        "reports/source_label_crosstab.csv",
        (
            field("split", enum_name="QuerySplit"),
            field("source_combination"),
            field("label", FieldType.INTEGER, numeric_min=0, numeric_max=1),
            field("count", FieldType.INTEGER, numeric_min=0),
        ),
        ("split", "source_combination", "label"),
        ("split", "source_combination", "label"),
    ),
    csv_schema(
        "reports/evidence_type_crosstab.csv",
        (
            field("split", enum_name="QuerySplit"),
            field("evidence_type_combination"),
            field("label", FieldType.INTEGER, numeric_min=0, numeric_max=1),
            field("count", FieldType.INTEGER, numeric_min=0),
        ),
        ("split", "evidence_type_combination", "label"),
        ("split", "evidence_type_combination", "label"),
    ),
    csv_schema(
        "reports/descriptor_summary.csv",
        (
            field("split", enum_name="QuerySplit"),
            field("descriptor"),
            field("count", FieldType.INTEGER, numeric_min=0),
            field("missing", FieldType.INTEGER, numeric_min=0),
            field("mean", FieldType.FLOAT, nullable=True),
            field("std", FieldType.FLOAT, nullable=True),
            field("min", FieldType.FLOAT, nullable=True),
            field("p05", FieldType.FLOAT, nullable=True),
            field("p25", FieldType.FLOAT, nullable=True),
            field("median", FieldType.FLOAT, nullable=True),
            field("p75", FieldType.FLOAT, nullable=True),
            field("p95", FieldType.FLOAT, nullable=True),
            field("max", FieldType.FLOAT, nullable=True),
            field("summary_status", enum_name="SummaryStatus"),
        ),
        ("split", "descriptor"),
        ("split", "descriptor"),
    ),
    csv_schema(
        "reports/descriptor_failures.csv",
        (
            field("compound_id"),
            field("query_split", enum_name="QuerySplit"),
            field("descriptor"),
            field("error_reason"),
        ),
        ("compound_id", "query_split", "descriptor"),
        ("query_split", "compound_id", "descriptor"),
    ),
    csv_schema(
        "reports/scaffold_summary.csv",
        (
            field("split", enum_name="QuerySplit"),
            field("unique_scaffold_count", FieldType.INTEGER, numeric_min=0),
            field("singleton_scaffold_count", FieldType.INTEGER, numeric_min=0),
            field(
                "singleton_scaffold_rate",
                FieldType.FLOAT,
                nullable=True,
                numeric_min=0,
                numeric_max=1,
            ),
            field(
                "compound_weighted_overlap",
                FieldType.FLOAT,
                nullable=True,
                numeric_min=0,
                numeric_max=1,
            ),
            field(
                "scaffold_weighted_overlap",
                FieldType.FLOAT,
                nullable=True,
                numeric_min=0,
                numeric_max=1,
            ),
            field("status", enum_name="ScaffoldSummaryStatus"),
        ),
        ("split",),
        ("split",),
    ),
    csv_schema(
        "reports/similarity_summary.csv",
        (
            field("query_split", enum_name="QuerySplit"),
            field("count", FieldType.INTEGER, numeric_min=0),
            field("missing", FieldType.INTEGER, numeric_min=0),
            field(
                "mean", FieldType.FLOAT, nullable=True, numeric_min=0, numeric_max=1
            ),
            field(
                "median",
                FieldType.FLOAT,
                nullable=True,
                numeric_min=0,
                numeric_max=1,
            ),
            field(
                "p95", FieldType.FLOAT, nullable=True, numeric_min=0, numeric_max=1
            ),
            field(
                "max", FieldType.FLOAT, nullable=True, numeric_min=0, numeric_max=1
            ),
            field("summary_status", enum_name="SummaryStatus"),
        ),
        ("query_split",),
        ("query_split",),
    ),
    csv_schema(
        "reports/source_label_association.csv",
        (
            field("split", enum_name="QuerySplit"),
            field("chi2_statistic", FieldType.FLOAT, nullable=True, numeric_min=0),
            field(
                "chi2_pvalue",
                FieldType.FLOAT,
                nullable=True,
                numeric_min=0,
                numeric_max=1,
            ),
            field("cramers_v", FieldType.FLOAT, numeric_min=0, numeric_max=1),
            field("effective_rows", FieldType.INTEGER, numeric_min=0),
            field("effective_columns", FieldType.INTEGER, numeric_min=0),
            field("test_status", enum_name="TestStatus"),
            field("source_label_confounding_warning", FieldType.BOOLEAN),
        ),
        ("split",),
        ("split",),
    ),
    csv_schema(
        "reports/distribution_shift.csv",
        (
            field("comparison_split", enum_name="QuerySplit"),
            field("descriptor"),
            field("smd", FieldType.FLOAT, nullable=True),
            field("smd_status", enum_name="SmdStatus"),
            field(
                "ks_statistic",
                FieldType.FLOAT,
                nullable=True,
                numeric_min=0,
                numeric_max=1,
            ),
            field(
                "ks_pvalue",
                FieldType.FLOAT,
                nullable=True,
                numeric_min=0,
                numeric_max=1,
            ),
            field("test_status", enum_name="TestStatus"),
        ),
        ("comparison_split", "descriptor"),
        ("comparison_split", "descriptor"),
    ),
    csv_schema(
        "reports/development_exact_block_set.csv",
        (
            field("standardized_inchikey", FieldType.INCHIKEY),
            field("compound_id"),
            field("source_dataset", enum_name="SourceDataset"),
            field("record_key"),
        ),
        ("standardized_inchikey", "compound_id", "source_dataset", "record_key"),
        ("standardized_inchikey", "compound_id", "source_dataset", "record_key"),
    ),
    csv_schema(
        "reports/development_connectivity_block_set.csv",
        (
            field("connectivity_key"),
            field("contribution_type", enum_name="LeakageContributionType"),
            field("contributor_id"),
            field("source_dataset", enum_name="SourceDataset"),
        ),
        ("connectivity_key", "contribution_type", "contributor_id", "source_dataset"),
        ("connectivity_key", "contribution_type", "contributor_id", "source_dataset"),
    ),
    json_schema(
        "reports/leakage_audit.json",
        (
            field("schema_version"),
            field("development_exact_block_count", FieldType.INTEGER, numeric_min=0),
            field(
                "development_connectivity_block_count",
                FieldType.INTEGER,
                numeric_min=0,
            ),
            field("primary_external_count", FieldType.INTEGER, numeric_min=0),
            field("exact_overlap_count", FieldType.INTEGER, numeric_min=0),
            field("connectivity_overlap_count", FieldType.INTEGER, numeric_min=0),
            field(
                "train_validation_connectivity_overlap_count",
                FieldType.INTEGER,
                numeric_min=0,
            ),
            field("status", enum_name="SummaryStatus"),
        ),
    ),
    json_schema(
        "reports/resolution_summary.json",
        (
            field("schema_version"),
            field("record_count", FieldType.INTEGER, numeric_min=0),
            field("compound_count", FieldType.INTEGER, numeric_min=0),
            field("role_resolution_count", FieldType.INTEGER, numeric_min=0),
            field("conflict_count", FieldType.INTEGER, numeric_min=0),
            field("structure_conflict_count", FieldType.INTEGER, numeric_min=0),
            field("eligible_development_count", FieldType.INTEGER, numeric_min=0),
            field("eligible_external_count", FieldType.INTEGER, numeric_min=0),
            field("status", enum_name="SummaryStatus"),
        ),
    ),
    csv_schema(
        "reports/modeling_conflict_review_candidates.csv",
        (
            field("compound_id"),
            field("dataset_role", enum_name="DatasetRole"),
            field("clear_positive_count", FieldType.INTEGER, numeric_min=0),
            field("clear_negative_count", FieldType.INTEGER, numeric_min=0),
            field("record_keys_json", FieldType.JSON, canonical_array=True),
            field("review_status", enum_name="ReviewStatus"),
            field("decision", enum_name="ReviewDecision"),
            field("resolved_label", FieldType.INTEGER, nullable=True, numeric_min=0, numeric_max=1),
            field("resolution_reason"),
        ),
        ("compound_id", "dataset_role"),
        ("compound_id", "dataset_role"),
        artifact_class=ArtifactClass.AUDIT_ONLY,
    ),
)


SCHEMA_REGISTRY: dict[str, ArtifactSchema] = {
    schema.path: schema for schema in ARTIFACT_SCHEMAS
}


def validate_registry() -> None:
    """验证注册表内部没有路径、列或键定义错误。"""

    if len(SCHEMA_REGISTRY) != len(ARTIFACT_SCHEMAS):
        raise ValueError("artifact 注册表存在重复路径")
    for schema in ARTIFACT_SCHEMAS:
        columns = schema.columns
        if len(columns) != len(set(columns)):
            raise ValueError(f"{schema.path} 存在重复列")
        if not columns:
            raise ValueError(f"artifact 缺少字段 schema：{schema.path}")
        for key in schema.unique_key + schema.sort_key:
            if key not in columns:
                raise ValueError(f"{schema.path} 的键字段未注册：{key}")
        if not schema.path or schema.path.startswith("/") or ".." in schema.path.split("/"):
            raise ValueError(f"artifact 路径不安全：{schema.path}")
        for spec in schema.fields:
            if spec.enum_name is not None and spec.enum_name not in ENUM_TYPES:
                raise ValueError(
                    f"{schema.path} 引用了未注册枚举：{spec.enum_name}"
                )
            if (
                spec.numeric_min is not None
                and spec.numeric_max is not None
                and spec.numeric_min > spec.numeric_max
            ):
                raise ValueError(f"{schema.path}.{spec.name} 数值范围相反")
    for field_name, rank_map in ENUM_RANKS.items():
        enum_name = "DatasetRole" if field_name == "dataset_role" else "QuerySplit"
        expected_values = {item.value for item in ENUM_TYPES[enum_name]}
        if set(rank_map) != expected_values:
            raise ValueError(f"枚举排序 rank 不完整：{field_name}")


validate_registry()
