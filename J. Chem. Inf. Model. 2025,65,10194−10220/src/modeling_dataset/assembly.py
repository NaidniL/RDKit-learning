"""阶段 2 全部确定性 artifacts 的单一组装入口。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .core_pipeline import CoreBuild, validate_core
from .fingerprint import FIXED_ASSEMBLY_PARAMETERS, input_fingerprint
from .manifests import AUDIT_ONLY_PATHS, RELEASE_PATHS
from .reports import ReportsBuild, build_reports
from .schema_registry import ArtifactFormat, SCHEMA_REGISTRY, SCHEMA_VERSION
from .serialization import canonical_json_bytes, serialize_csv
from .splits import SplitBuild, build_splits
from .structure_relations import build_structure_relation_edges
from .validation import validate_row


ASSEMBLY_FINGERPRINT_PARAMETERS = {
    "implementation_batch": 4,
    "schema_version": SCHEMA_VERSION,
    "workflow": "dataset_assembly_v1",
}


@dataclass(frozen=True)
class AssemblyBuild:
    input_fingerprint: str
    runtime_signature: dict[str, str]
    settings: dict[str, Any]
    release_payloads: dict[str, bytes]
    audit_only_payloads: dict[str, bytes]
    core: CoreBuild
    splits: SplitBuild
    reports: ReportsBuild
    relation_edge_count: int


def _csv_payload(path: str, rows: list[dict[str, Any]]) -> bytes:
    return serialize_csv(rows, SCHEMA_REGISTRY[path])


def _json_payload(path: str, value: Mapping[str, Any]) -> bytes:
    schema = SCHEMA_REGISTRY[path]
    if schema.artifact_format is not ArtifactFormat.JSON:
        raise AssertionError(f"artifact 不是 JSON：{path}")
    validate_row(value, schema)
    return canonical_json_bytes(dict(value))


def _conflict_artifacts(
    core: CoreBuild,
) -> tuple[bytes, list[dict[str, Any]], list[dict[str, Any]]]:
    decisions = [
        {
            "compound_id": row["compound_id"],
            "dataset_role": row["dataset_role"],
            "clear_positive_count": row["clear_positive_count"],
            "clear_negative_count": row["clear_negative_count"],
            "decision": row["decision"],
            "resolved_label": row["resolved_label"],
            "resolution_reason": row["resolution_reason"],
        }
        for row in core.review_candidates
    ]
    decision_payload = _csv_payload("modeling/conflict_reviews.csv", decisions)
    label_conflicts = [
        {
            "compound_id": row["compound_id"],
            "dataset_role": row["dataset_role"],
            "clear_positive_count": row["clear_positive_count"],
            "clear_negative_count": row["clear_negative_count"],
            "decision": row["decision"],
            "resolved_label": row["resolved_label"],
            "resolution_reason": row["resolution_reason"],
        }
        for row in core.review_candidates
    ]
    return decision_payload, label_conflicts, core.review_candidates


def _split_payload_rows(splits: SplitBuild) -> dict[str, list[dict[str, Any]]]:
    return {
        "splits/primary_reproduction/train.csv": splits.train,
        "splits/primary_reproduction/validation.csv": splits.validation,
        "splits/primary_reproduction/train_tuning_cv_folds.csv": (
            splits.train_tuning_folds
        ),
        "splits/full_development_stratified_cv_folds.csv": (
            splits.full_development_stratified_folds
        ),
        "splits/full_development_scaffold_cv_folds.csv": (
            splits.full_development_scaffold_folds
        ),
        "splits/external_test.csv": splits.external_test,
        "splits/external_test_tautomer_clean_sensitivity.csv": (
            splits.external_tautomer_sensitivity
        ),
    }


def _report_payload_rows(reports: ReportsBuild) -> dict[str, list[dict[str, Any]]]:
    return {
        "reports/nearest_neighbors.csv": reports.nearest_neighbors,
        "reports/split_summary.csv": reports.split_summary,
        "reports/source_label_crosstab.csv": reports.source_label_crosstab,
        "reports/evidence_type_crosstab.csv": reports.evidence_type_crosstab,
        "reports/source_label_association.csv": reports.source_label_association,
        "reports/descriptor_summary.csv": reports.descriptor_summary,
        "reports/descriptor_failures.csv": reports.descriptor_failures,
        "reports/scaffold_summary.csv": reports.scaffold_summary,
        "reports/similarity_summary.csv": reports.similarity_summary,
        "reports/distribution_shift.csv": reports.distribution_shift,
    }


def build_assembly(root: Path, *, require_formal: bool = False) -> AssemblyBuild:
    """重建完整 release 候选字节，不写入任何输出目录。"""

    fingerprint, descriptor = input_fingerprint(
        root, parameters=ASSEMBLY_FINGERPRINT_PARAMETERS
    )
    core = validate_core(root)
    conflict_payload, label_conflicts, candidates = _conflict_artifacts(core)
    splits = build_splits(
        root,
        core.compounds,
        core.finalized_role_resolutions,
        core.leakage,
    )
    relation_edges, discordant_edges = build_structure_relation_edges(
        core.compounds,
        core.finalized_role_resolutions,
        core.fingerprints,
    )
    split_mapping = {
        "train": splits.train,
        "validation": splits.validation,
        "external_test": splits.external_test,
        "external_tautomer_sensitivity": splits.external_tautomer_sensitivity,
    }
    reports = build_reports(
        split_mapping,
        core.compounds,
        core.fingerprints,
        core.finalized_role_resolutions,
        core.records_all,
    )
    compound_map = {str(row["compound_id"]): row for row in core.compounds}
    train_connectivity = {
        str(compound_map[str(row["compound_id"])]["connectivity_key"])
        for row in splits.train
    }
    validation_connectivity = {
        str(compound_map[str(row["compound_id"])]["connectivity_key"])
        for row in splits.validation
    }
    leakage_audit = {
        "schema_version": SCHEMA_VERSION,
        "development_exact_block_count": len(core.leakage.exact_block_keys),
        "development_connectivity_block_count": len(
            core.leakage.connectivity_block_keys
        ),
        "primary_external_count": len(core.leakage.primary_external_ids),
        "exact_overlap_count": core.summary["external_exact_overlap_count"],
        "connectivity_overlap_count": core.summary[
            "external_connectivity_overlap_count"
        ],
        "train_validation_connectivity_overlap_count": len(
            train_connectivity & validation_connectivity
        ),
        "status": "ok",
    }
    resolution_summary = {
        "schema_version": SCHEMA_VERSION,
        "record_count": len(core.records_all),
        "compound_count": len(core.compounds),
        "role_resolution_count": len(core.finalized_role_resolutions),
        "conflict_count": core.summary["conflict_count"],
        "structure_conflict_count": sum(
            "structure_representation_conflict" in row["structure_reasons_json"]
            for row in core.compounds
        ),
        "eligible_development_count": len(splits.train) + len(splits.validation),
        "eligible_external_count": len(splits.external_test),
        "status": "ok",
    }
    rows_by_path: dict[str, list[dict[str, Any]]] = {
        "modeling/records_all.csv": core.records_all,
        "modeling/compounds.csv": core.compounds,
        "modeling/compound_role_resolutions.csv": core.finalized_role_resolutions,
        "modeling/compound_exclusions.csv": core.compound_exclusions,
        "modeling/record_exclusions.csv": core.record_exclusions,
        "modeling/duplicate_groups.csv": core.duplicate_groups,
        "modeling/structure_relation_edges.csv": relation_edges,
        "reports/label_conflicts.csv": label_conflicts,
        "reports/cross_role_tautomer_overlaps.csv": (
            core.leakage.tautomer_overlap_rows
        ),
        "reports/label_discordant_near_neighbors.csv": discordant_edges,
        "reports/development_exact_block_set.csv": core.leakage.exact_block_rows,
        "reports/development_connectivity_block_set.csv": (
            core.leakage.connectivity_block_rows
        ),
        **_split_payload_rows(splits),
        **_report_payload_rows(reports),
    }
    release_payloads = {
        path: _csv_payload(path, rows) for path, rows in rows_by_path.items()
    }
    release_payloads["modeling/conflict_reviews.csv"] = conflict_payload
    release_payloads["reports/leakage_audit.json"] = _json_payload(
        "reports/leakage_audit.json", leakage_audit
    )
    release_payloads["reports/resolution_summary.json"] = _json_payload(
        "reports/resolution_summary.json", resolution_summary
    )
    if set(release_payloads) != RELEASE_PATHS:
        raise AssertionError(
            "release payload 集合与 registry 不一致；"
            f"缺少={sorted(RELEASE_PATHS - set(release_payloads))}，"
            f"多出={sorted(set(release_payloads) - RELEASE_PATHS)}"
        )
    audit_only_payloads = {
        "reports/modeling_conflict_review_candidates.csv": _csv_payload(
            "reports/modeling_conflict_review_candidates.csv", candidates
        )
    }
    if set(audit_only_payloads) != AUDIT_ONLY_PATHS:
        raise AssertionError("audit-only payload 集合与 registry 不一致")
    settings = {
        "fixed_parameters": FIXED_ASSEMBLY_PARAMETERS,
        "schema_version": SCHEMA_VERSION,
        "automatic_resolution_count": core.summary["automatic_resolution_count"],
        "automatic_exclusion_count": core.summary["automatic_exclusion_count"],
        "source_label_confounding_warning": (
            reports.source_label_confounding_warning
        ),
        "external_lock": {
            "default_access": "denied",
            "required_mode": "external_final",
            "primary_count": len(splits.external_test),
            "sensitivity_count": len(splits.external_tautomer_sensitivity),
        },
    }
    runtime = descriptor["runtime_signature"]
    if not isinstance(runtime, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in runtime.items()
    ):
        raise AssertionError("input descriptor runtime_signature 类型非法")
    return AssemblyBuild(
        input_fingerprint=fingerprint,
        runtime_signature=dict(runtime),
        settings=settings,
        release_payloads=release_payloads,
        audit_only_payloads=audit_only_payloads,
        core=core,
        splits=splits,
        reports=reports,
        relation_edge_count=len(relation_edges),
    )
