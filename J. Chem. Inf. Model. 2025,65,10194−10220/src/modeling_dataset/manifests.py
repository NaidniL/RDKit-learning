"""audit/formal manifest 构建和 release 完整性校验。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from .paths import secure_join, validate_relative_path
from .schema_registry import ArtifactClass, ArtifactFormat, SCHEMA_REGISTRY
from .serialization import (
    FileDigest,
    canonical_json_bytes,
    digest_file,
    write_bytes_fsync,
)
from .validation import (
    collect_regular_files,
    read_and_validate_csv,
    read_and_validate_json,
    validate_manifest_maps,
)


MANIFEST_VERSION = 1
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
RELEASE_PATHS = {
    path
    for path, schema in SCHEMA_REGISTRY.items()
    if schema.artifact_class is ArtifactClass.RELEASE
}
AUDIT_ONLY_PATHS = {
    path
    for path, schema in SCHEMA_REGISTRY.items()
    if schema.artifact_class is ArtifactClass.AUDIT_ONLY
}


def artifact_metadata(root: Path, relative_path: str) -> dict[str, Any]:
    schema = SCHEMA_REGISTRY.get(relative_path)
    if schema is None:
        raise ValueError(f"artifact 未在 schema registry 注册：{relative_path}")
    path = secure_join(root, relative_path, must_exist=True)
    digest = digest_file(
        path,
        csv_rows=schema.artifact_format is ArtifactFormat.CSV,
    )
    if schema.artifact_format is ArtifactFormat.CSV:
        read_and_validate_csv(path, schema)
    else:
        read_and_validate_json(path, schema)
    result: dict[str, Any] = {
        "sha256": digest.sha256,
        "bytes": digest.bytes,
        "schema_version": schema.schema_version,
    }
    if digest.rows is not None:
        result["rows"] = digest.rows
    return result


def build_artifact_map(root: Path, relative_paths: set[str]) -> dict[str, dict[str, Any]]:
    return {
        path: artifact_metadata(root, path)
        for path in sorted(relative_paths)
    }


def build_manifest(
    *,
    run_id: str,
    run_type: str,
    input_fingerprint: str,
    runtime_signature: Mapping[str, str],
    settings: Mapping[str, Any],
    release_artifacts: Mapping[str, Mapping[str, Any]],
    audit_only_artifacts: Mapping[str, Mapping[str, Any]],
    log_path: str,
    log_digest: FileDigest,
    approved_audit_run: str = "",
) -> dict[str, Any]:
    if run_type not in {"audit", "formal"}:
        raise ValueError(f"未知 run_type：{run_type}")
    validate_relative_path(log_path)
    validate_manifest_maps(release_artifacts, audit_only_artifacts)
    return {
        "manifest_version": MANIFEST_VERSION,
        "run_id": run_id,
        "run_type": run_type,
        "approved_audit_run": approved_audit_run,
        "input_fingerprint": input_fingerprint,
        "runtime_signature": dict(runtime_signature),
        "settings": dict(settings),
        "release_artifacts": dict(release_artifacts),
        "audit_only_artifacts": dict(audit_only_artifacts),
        "log": {
            "path": log_path,
            "sha256": log_digest.sha256,
            "bytes": log_digest.bytes,
        },
    }


def write_manifest(path: Path, manifest: Mapping[str, Any]) -> FileDigest:
    """写入 manifest；manifest 不记录自身哈希。"""

    payload = canonical_json_bytes(dict(manifest))
    write_bytes_fsync(path, payload)
    return digest_file(path)


def load_manifest(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest 无法读取：{path}") from exc
    if not isinstance(value, dict):
        raise ValueError("manifest 顶层必须是对象")
    required = {
        "manifest_version",
        "run_id",
        "run_type",
        "approved_audit_run",
        "input_fingerprint",
        "runtime_signature",
        "settings",
        "release_artifacts",
        "audit_only_artifacts",
        "log",
    }
    if set(value) != required:
        raise ValueError("manifest 字段集合不正确")
    if value["manifest_version"] != MANIFEST_VERSION:
        raise ValueError("manifest_version 不受支持")
    if raw != canonical_json_bytes(value):
        raise ValueError("manifest 不是 canonical JSON 或缺少唯一 LF 结尾")
    if not isinstance(value["release_artifacts"], dict) or not isinstance(
        value["audit_only_artifacts"], dict
    ):
        raise ValueError("manifest artifact map 类型错误")
    validate_manifest_maps(
        value["release_artifacts"], value["audit_only_artifacts"]
    )
    if value["run_type"] not in {"audit", "formal"}:
        raise ValueError("manifest run_type 非法")
    if not isinstance(value["run_id"], str) or not RUN_ID_PATTERN.fullmatch(
        value["run_id"]
    ):
        raise ValueError("manifest run_id 非法")
    if not isinstance(value["input_fingerprint"], str) or not SHA256_PATTERN.fullmatch(
        value["input_fingerprint"]
    ):
        raise ValueError("manifest input_fingerprint 非法")
    if not isinstance(value["runtime_signature"], dict) or not isinstance(
        value["settings"], dict
    ):
        raise ValueError("manifest runtime_signature/settings 类型非法")
    log = value["log"]
    if not isinstance(log, dict) or set(log) != {"path", "sha256", "bytes"}:
        raise ValueError("manifest log 元数据字段非法")
    validate_relative_path(log["path"])
    if not isinstance(log["sha256"], str) or not SHA256_PATTERN.fullmatch(
        log["sha256"]
    ):
        raise ValueError("manifest log SHA-256 非法")
    if type(log["bytes"]) is not int or log["bytes"] < 0:
        raise ValueError("manifest log 字节数非法")
    if value["run_type"] == "formal":
        if not isinstance(value["approved_audit_run"], str) or not value[
            "approved_audit_run"
        ]:
            raise ValueError("formal manifest 缺少 approved_audit_run")
        if set(value["release_artifacts"]) != RELEASE_PATHS:
            raise ValueError("formal manifest 未覆盖全部正式 release artifacts")
        if value["audit_only_artifacts"]:
            raise ValueError("formal manifest 不得包含 audit-only artifacts")
        if log["path"] != "formal.log":
            raise ValueError("formal manifest 日志路径必须是 formal.log")
    else:
        if value["approved_audit_run"] != "":
            raise ValueError("audit manifest 不得设置 approved_audit_run")
        if log["path"] != "audit.log":
            raise ValueError("audit manifest 日志路径必须是 audit.log")
        if set(value["release_artifacts"]) != RELEASE_PATHS:
            raise ValueError("audit manifest 未覆盖全部正式候选 artifacts")
        if set(value["audit_only_artifacts"]) != AUDIT_ONLY_PATHS:
            raise ValueError("audit manifest 未覆盖全部 audit-only artifacts")
    _validate_metadata_map(value["release_artifacts"], include_rows=True)
    _validate_metadata_map(value["audit_only_artifacts"], include_rows=True)
    return value


def _validate_metadata_map(
    artifact_map: Mapping[str, Mapping[str, Any]], *, include_rows: bool
) -> None:
    for relative_path, metadata in artifact_map.items():
        schema = SCHEMA_REGISTRY[relative_path]
        expected = {"sha256", "bytes", "schema_version"}
        if include_rows and schema.artifact_format is ArtifactFormat.CSV:
            expected.add("rows")
        if not isinstance(metadata, dict) or set(metadata) != expected:
            raise ValueError(f"artifact 元数据字段非法：{relative_path}")
        if not isinstance(metadata["sha256"], str) or not SHA256_PATTERN.fullmatch(
            metadata["sha256"]
        ):
            raise ValueError(f"artifact SHA-256 格式非法：{relative_path}")
        if type(metadata["bytes"]) is not int or metadata["bytes"] < 0:
            raise ValueError(f"artifact 字节数非法：{relative_path}")
        if metadata["schema_version"] != schema.schema_version:
            raise ValueError(f"artifact schema_version 非法：{relative_path}")
        if "rows" in expected and (
            type(metadata["rows"]) is not int or metadata["rows"] < 0
        ):
            raise ValueError(f"artifact 逻辑行数非法：{relative_path}")


def _compare_digest(
    relative_path: str, actual: FileDigest, metadata: Mapping[str, Any]
) -> None:
    if actual.sha256 != metadata.get("sha256"):
        raise ValueError(f"artifact SHA-256 不一致：{relative_path}")
    if actual.bytes != metadata.get("bytes"):
        raise ValueError(f"artifact 字节数不一致：{relative_path}")
    if actual.rows is not None and actual.rows != metadata.get("rows"):
        raise ValueError(f"artifact 逻辑行数不一致：{relative_path}")


def verify_artifact_map(
    release_root: Path, artifact_map: Mapping[str, Mapping[str, Any]]
) -> None:
    for relative_path, metadata in artifact_map.items():
        schema = SCHEMA_REGISTRY.get(relative_path)
        if schema is None:
            raise ValueError(f"manifest 引用了未注册 artifact：{relative_path}")
        path = secure_join(release_root, relative_path, must_exist=True)
        if schema.artifact_format is ArtifactFormat.CSV:
            read_and_validate_csv(path, schema, formal=True)
        else:
            read_and_validate_json(path, schema)
        actual = digest_file(
            path,
            csv_rows=schema.artifact_format is ArtifactFormat.CSV,
        )
        if metadata.get("schema_version") != schema.schema_version:
            raise ValueError(f"artifact schema_version 不一致：{relative_path}")
        _compare_digest(relative_path, actual, metadata)


def verify_release_directory(release_root: Path, manifest: Mapping[str, Any]) -> None:
    release_map = manifest["release_artifacts"]
    if not isinstance(release_map, dict):
        raise ValueError("formal manifest 的 release_artifacts 类型错误")
    if set(release_map) != RELEASE_PATHS:
        raise ValueError("正式 release 未包含全部注册 artifacts")
    verify_artifact_map(release_root, release_map)
    log = manifest.get("log")
    if not isinstance(log, dict) or not isinstance(log.get("path"), str):
        raise ValueError("manifest log 元数据非法")
    log_path = secure_join(release_root, log["path"], must_exist=True)
    _compare_digest(log["path"], digest_file(log_path), log)
    expected_files = set(release_map) | {"manifest.json", str(log["path"])}
    actual_files = collect_regular_files(release_root)
    if actual_files != expected_files:
        raise ValueError(
            "正式 release 文件集合不一致；"
            f"缺少={sorted(expected_files - actual_files)}，"
            f"多出={sorted(actual_files - expected_files)}"
        )


def verify_current_release(releases_root: Path) -> tuple[Path, dict[str, Any]]:
    """验证 pointer、manifest、日志和全部正式 artifacts。"""

    pointer_path = secure_join(
        releases_root, "current_release.json", must_exist=True
    )
    pointer_raw = pointer_path.read_bytes()
    try:
        pointer = json.loads(pointer_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("current_release.json 不是合法 JSON") from exc
    if pointer_raw != canonical_json_bytes(pointer):
        raise ValueError("current_release.json 不是 canonical JSON")
    if not isinstance(pointer, dict) or set(pointer) != {
        "release_id",
        "manifest_path",
        "manifest_sha256",
    }:
        raise ValueError("current_release.json schema 非法")
    release_id = pointer["release_id"]
    manifest_relative = pointer["manifest_path"]
    if not isinstance(release_id, str) or not isinstance(manifest_relative, str):
        raise ValueError("pointer 字段类型错误")
    if not RUN_ID_PATTERN.fullmatch(release_id):
        raise ValueError("pointer release_id 格式非法")
    manifest_sha = pointer["manifest_sha256"]
    if not isinstance(manifest_sha, str) or not SHA256_PATTERN.fullmatch(
        manifest_sha
    ):
        raise ValueError("pointer manifest_sha256 格式非法")
    expected_manifest_path = f"{release_id}/manifest.json"
    if manifest_relative != expected_manifest_path:
        raise ValueError("pointer manifest_path 与 release_id 不一致")
    manifest_path = secure_join(
        releases_root, manifest_relative, must_exist=True
    )
    manifest_digest = digest_file(manifest_path)
    if manifest_digest.sha256 != pointer["manifest_sha256"]:
        raise ValueError("pointer 中的 manifest SHA-256 不一致")
    manifest = load_manifest(manifest_path)
    if manifest.get("run_id") != release_id or manifest.get("run_type") != "formal":
        raise ValueError("pointer 指向的 manifest run 信息不一致")
    release_root = manifest_path.parent
    verify_release_directory(release_root, manifest)
    return release_root, manifest
