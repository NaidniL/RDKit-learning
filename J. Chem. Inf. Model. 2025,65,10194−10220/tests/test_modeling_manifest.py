"""manifest、行级 schema 与 release 篡改检测测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.enums import (  # noqa: E402
    ControlledStringEnum,
    ENUM_TYPES,
)
from modeling_dataset.manifests import (  # noqa: E402
    RELEASE_PATHS,
    artifact_metadata,
    build_artifact_map,
    build_manifest,
    load_manifest,
    verify_current_release,
    verify_release_directory,
    write_manifest,
)
from modeling_dataset.schema_registry import (  # noqa: E402
    ArtifactFormat,
    FieldSpec,
    FieldType,
    SCHEMA_REGISTRY,
)
from modeling_dataset.serialization import (  # noqa: E402
    canonical_json_bytes,
    digest_file,
    serialize_csv,
)
from modeling_dataset.validation import validate_manifest_maps  # noqa: E402


def minimal_value(spec: FieldSpec) -> Any:
    if spec.enum_name is not None:
        member = next(iter(ENUM_TYPES[spec.enum_name]))
        return cast(ControlledStringEnum, member).value
    if spec.field_type is FieldType.INTEGER:
        return int(spec.numeric_min or 0)
    if spec.field_type is FieldType.FLOAT:
        return float(spec.numeric_min or 0)
    if spec.field_type is FieldType.BOOLEAN:
        return False
    if spec.field_type is FieldType.JSON:
        return [] if spec.canonical_array else {}
    if spec.field_type is FieldType.UTC_TIME:
        return "2026-07-05T00:00:00Z"
    if spec.field_type is FieldType.INCHIKEY:
        return "AAAAAAAAAAAAAA-BBBBBBBBBB-C"
    return "1.0.0" if spec.name == "schema_version" else "x"


def write_all_release_artifacts(root: Path) -> None:
    for relative_path in sorted(RELEASE_PATHS):
        schema = SCHEMA_REGISTRY[relative_path]
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if schema.artifact_format is ArtifactFormat.CSV:
            path.write_bytes(serialize_csv([], schema))
        else:
            payload = {spec.name: minimal_value(spec) for spec in schema.fields}
            path.write_bytes(canonical_json_bytes(payload))


def make_release(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    root = tmp_path / "release-1"
    write_all_release_artifacts(root)
    (root / "formal.log").write_text("正式日志已封口\n", encoding="utf-8")
    release_map = build_artifact_map(root, RELEASE_PATHS)
    manifest = build_manifest(
        run_id="release-1",
        run_type="formal",
        approved_audit_run="audit-1",
        input_fingerprint="a" * 64,
        runtime_signature={"python": "3.10"},
        settings={"batch": 1},
        release_artifacts=release_map,
        audit_only_artifacts={},
        log_path="formal.log",
        log_digest=digest_file(root / "formal.log"),
    )
    write_manifest(root / "manifest.json", manifest)
    return root, manifest


def test_manifest_roundtrip_and_release_verification(tmp_path: Path) -> None:
    root, manifest = make_release(tmp_path)
    loaded = load_manifest(root / "manifest.json")
    assert loaded == manifest
    assert "manifest_sha256" not in loaded
    verify_release_directory(root, loaded)


@pytest.mark.parametrize("mode", ["missing", "extra", "tampered"])
def test_manifest_rejects_missing_extra_or_tampered_files(
    tmp_path: Path, mode: str
) -> None:
    root, manifest = make_release(tmp_path)
    artifact = root / "reports" / "resolution_summary.json"
    if mode == "missing":
        artifact.unlink()
    elif mode == "extra":
        (root / "unexpected.txt").write_text("x", encoding="utf-8")
    else:
        artifact.write_text('{"status":"tampered"}\n', encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_release_directory(root, manifest)


def test_artifact_metadata_rejects_illegal_row_value(tmp_path: Path) -> None:
    root = tmp_path / "release"
    schema = SCHEMA_REGISTRY["modeling/conflict_reviews.csv"]
    row = {
        "compound_id": "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-C",
        "dataset_role": "development",
        "clear_positive_count": "12",
        "clear_negative_count": "1",
        "decision": "include_positive",
        "resolved_label": "1",
        "resolution_reason": "非法决定",
    }
    path = root / schema.path
    path.parent.mkdir(parents=True)
    header = ",".join(schema.columns)
    path.write_text(header + "\n" + ",".join(row.values()) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ReviewDecision"):
        artifact_metadata(root, schema.path)


def test_json_report_requires_exact_object_schema(tmp_path: Path) -> None:
    root = tmp_path / "release"
    relative = "reports/resolution_summary.json"
    path = root / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(canonical_json_bytes([]))
    with pytest.raises(ValueError, match="顶层必须是对象"):
        artifact_metadata(root, relative)
    path.write_bytes(canonical_json_bytes({"status": "ok"}))
    with pytest.raises(ValueError, match="字段集合"):
        artifact_metadata(root, relative)


def test_release_and_audit_only_maps_validate_registry_class() -> None:
    candidate = "reports/modeling_conflict_review_candidates.csv"
    with pytest.raises(ValueError, match="路径重叠"):
        validate_manifest_maps({candidate: {}}, {candidate: {}})
    with pytest.raises(ValueError, match="artifact class"):
        validate_manifest_maps({candidate: {}}, {})


def test_incomplete_formal_release_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "release"
    root.mkdir()
    (root / "formal.log").write_text("日志\n", encoding="utf-8")
    manifest = build_manifest(
        run_id="release",
        run_type="formal",
        approved_audit_run="audit",
        input_fingerprint="a" * 64,
        runtime_signature={},
        settings={},
        release_artifacts={},
        audit_only_artifacts={},
        log_path="formal.log",
        log_digest=digest_file(root / "formal.log"),
    )
    write_manifest(root / "manifest.json", manifest)
    with pytest.raises(ValueError, match="全部正式"):
        load_manifest(root / "manifest.json")


def test_empty_audit_manifest_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "audit"
    root.mkdir()
    (root / "audit.log").write_text("日志\n", encoding="utf-8")
    manifest = build_manifest(
        run_id="audit-1",
        run_type="audit",
        input_fingerprint="a" * 64,
        runtime_signature={},
        settings={},
        release_artifacts={},
        audit_only_artifacts={},
        log_path="audit.log",
        log_digest=digest_file(root / "audit.log"),
    )
    write_manifest(root / "audit_manifest.json", manifest)
    with pytest.raises(ValueError, match="全部正式候选"):
        load_manifest(root / "audit_manifest.json")


def test_pointer_and_artifact_tampering_are_rejected(tmp_path: Path) -> None:
    release, _ = make_release(tmp_path)
    releases_root = tmp_path
    manifest_path = release / "manifest.json"
    pointer_path = releases_root / "current_release.json"
    pointer = {
        "release_id": "release-1",
        "manifest_path": "release-1/manifest.json",
        "manifest_sha256": digest_file(manifest_path).sha256,
    }
    pointer_path.write_bytes(canonical_json_bytes(pointer))
    verify_current_release(releases_root)
    pointer["manifest_sha256"] = "0" * 64
    pointer_path.write_bytes(canonical_json_bytes(pointer))
    with pytest.raises(ValueError, match="manifest SHA-256"):
        verify_current_release(releases_root)
