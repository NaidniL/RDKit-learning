"""阶段 2 建模数据集组装、审计与正式发布入口。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.assembly import build_assembly  # noqa: E402
from modeling_dataset.core_pipeline import validate_core  # noqa: E402
from modeling_dataset.fingerprint import input_fingerprint  # noqa: E402
from modeling_dataset.manifests import (  # noqa: E402
    load_manifest,
    verify_audit_directory,
    verify_current_release,
)
from modeling_dataset.paths import secure_join  # noqa: E402
from modeling_dataset.schema_registry import (  # noqa: E402
    ARTIFACT_SCHEMAS,
    ArtifactFormat,
    SCHEMA_REGISTRY,
    validate_registry,
)
from modeling_dataset.serialization import canonical_json  # noqa: E402
from modeling_dataset.transaction import (  # noqa: E402
    AuditTransaction,
    ReleaseTransaction,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="阶段 2 可审计建模数据集组装")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-inputs", help="只读验证冻结输入并计算指纹")
    subparsers.add_parser("validate-core", help="纯内存重建来源、结构、角色与泄漏")
    audit = subparsers.add_parser("audit", help="生成 assembly dry-run 审计")
    audit.add_argument("--dry-run", action="store_true", required=True)
    audit.add_argument("--run-id", help="显式 audit run-id，仅用于可重现调用")
    formal = subparsers.add_parser("formal", help="从已批准 audit 生成正式 release")
    formal.add_argument("--approved-audit-run", required=True)
    formal.add_argument("--run-id", help="显式 formal run-id")
    return parser


def _run_id(prefix: str, fingerprint: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f_UTC")
    return f"{timestamp}_{prefix}_{fingerprint[:8]}"


def _payload_metadata(path: str, payload: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "schema_version": SCHEMA_REGISTRY[path].schema_version,
    }
    if SCHEMA_REGISTRY[path].artifact_format is ArtifactFormat.CSV:
        text = payload.decode("utf-8")
        result["rows"] = max(0, sum(1 for _ in csv.reader(io.StringIO(text))) - 1)
    return result


def _assert_equal_artifacts(
    payloads: Mapping[str, bytes], approved: Mapping[str, Mapping[str, Any]]
) -> None:
    if set(payloads) != set(approved):
        raise ValueError("重建的 release artifact 集合与已批准 audit 不一致")
    for path, payload in payloads.items():
        actual = _payload_metadata(path, payload)
        if actual != dict(approved[path]):
            raise ValueError(f"重建 artifact 与已批准 audit 不一致：{path}")


def _write_payloads(
    transaction: AuditTransaction | ReleaseTransaction,
    payloads: Mapping[str, bytes],
) -> None:
    for path in sorted(payloads):
        transaction.write_artifact(path, payloads[path])


def _run_audit(run_id: str | None) -> dict[str, Any]:
    build = build_assembly(ROOT, require_formal=False)
    actual_run_id = run_id or _run_id("audit", build.input_fingerprint)
    audits_root = ROOT / "audits" / "dataset_assembly"
    with AuditTransaction(audits_root, actual_run_id) as transaction:
        _write_payloads(transaction, build.release_payloads)
        _write_payloads(transaction, build.audit_only_payloads)
        transaction.log.write("阶段 2 dataset assembly dry-run")
        transaction.log.write(f"input_fingerprint={build.input_fingerprint}")
        transaction.log.write(
            "自动冲突裁决="
            f"{build.core.summary['automatic_resolution_count']}，"
            "自动排除="
            f"{build.core.summary['automatic_exclusion_count']}"
        )
        transaction.log.write(f"relation_edges={build.relation_edge_count}")
        audit_root = transaction.commit(
            input_fingerprint=build.input_fingerprint,
            runtime_signature=build.runtime_signature,
            settings=build.settings,
            release_artifact_paths=set(build.release_payloads),
            audit_only_artifact_paths=set(build.audit_only_payloads),
        )
    manifest = load_manifest(audit_root / "audit_manifest.json")
    verify_audit_directory(audit_root, manifest)
    return {
        "run_id": actual_run_id,
        "audit_root": audit_root.relative_to(ROOT).as_posix(),
        "input_fingerprint": build.input_fingerprint,
        "automatic_resolution_count": build.core.summary["automatic_resolution_count"],
        "automatic_exclusion_count": build.core.summary["automatic_exclusion_count"],
        "relation_edge_count": build.relation_edge_count,
        "status": "audit_created",
    }


def _run_formal(approved_run: str, run_id: str | None) -> dict[str, Any]:
    audits_root = ROOT / "audits" / "dataset_assembly"
    audit_root = secure_join(audits_root, approved_run, must_exist=True)
    audit_manifest = load_manifest(audit_root / "audit_manifest.json")
    if audit_manifest["run_id"] != approved_run:
        raise ValueError("已批准 audit run-id 与 manifest 不一致")
    verify_audit_directory(audit_root, audit_manifest)
    build = build_assembly(ROOT, require_formal=True)
    if build.input_fingerprint != audit_manifest["input_fingerprint"]:
        raise ValueError("当前输入指纹与已批准 audit 不一致")
    if build.runtime_signature != audit_manifest["runtime_signature"]:
        raise ValueError("当前运行环境与已批准 audit 不一致")
    if build.settings != audit_manifest["settings"]:
        raise ValueError("当前组装设置与已批准 audit 不一致")
    _assert_equal_artifacts(
        build.release_payloads, audit_manifest["release_artifacts"]
    )
    actual_run_id = run_id or _run_id("formal", build.input_fingerprint)
    releases_root = ROOT / "releases" / "dataset_assembly"
    with ReleaseTransaction(releases_root, actual_run_id) as transaction:
        _write_payloads(transaction, build.release_payloads)
        transaction.log.write("阶段 2 dataset assembly formal release")
        transaction.log.write(f"approved_audit_run={approved_run}")
        transaction.log.write(f"input_fingerprint={build.input_fingerprint}")
        release_root = transaction.commit(
            input_fingerprint=build.input_fingerprint,
            runtime_signature=build.runtime_signature,
            settings=build.settings,
            release_artifact_paths=set(build.release_payloads),
            approved_audit_run=approved_run,
        )
    verified_root, _ = verify_current_release(releases_root)
    if verified_root != release_root:
        raise AssertionError("current pointer 未指向新正式 release")
    return {
        "run_id": actual_run_id,
        "release_root": release_root.relative_to(ROOT).as_posix(),
        "approved_audit_run": approved_run,
        "input_fingerprint": build.input_fingerprint,
        "status": "formal_released",
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-inputs":
        validate_registry()
        fingerprint, descriptor = input_fingerprint(
            ROOT,
            parameters={"schema_count": len(ARTIFACT_SCHEMAS)},
        )
        print(
            canonical_json(
                {
                    "input_fingerprint": fingerprint,
                    "conflict_resolution": descriptor["conflict_resolution"],
                    "policy_sha256": descriptor["policy"]["sha256"],
                    "processed_file_count": len(descriptor["processed_files"]),
                    "schema_count": len(ARTIFACT_SCHEMAS),
                    "status": "validated",
                }
            )
        )
        return 0
    if args.command == "validate-core":
        validate_registry()
        result = validate_core(ROOT)
        print(canonical_json(result.summary))
        return 0
    if args.command == "audit":
        validate_registry()
        print(canonical_json(_run_audit(args.run_id)))
        return 0
    if args.command == "formal":
        validate_registry()
        print(canonical_json(_run_formal(args.approved_audit_run, args.run_id)))
        return 0
    raise AssertionError("argparse 返回了未知命令")


if __name__ == "__main__":
    raise SystemExit(main())
