"""单 release 原子事务和崩溃恢复测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.transaction import (  # noqa: E402
    ReleaseTransaction,
    SealedLog,
    SimulatedCrash,
)


def commit_empty_release(releases: Path, run_id: str) -> Path:
    with ReleaseTransaction(releases, run_id) as transaction:
        transaction.log.write("空 artifact release 事务测试")
        return transaction._commit_infrastructure_test_only()


def test_sealed_log_rejects_append(tmp_path: Path) -> None:
    log = SealedLog(tmp_path / "formal.log")
    log.write("第一行")
    digest = log.seal()
    assert digest.bytes > 0
    with pytest.raises(RuntimeError, match="已经封口"):
        log.write("禁止追加")


def test_empty_release_commit_and_pointer_verification(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    final = commit_empty_release(releases, "release-1")
    assert final.is_dir()
    pointer = releases / "current_transaction_test.json"
    assert pointer.is_file()
    assert (final / "transaction_manifest.json").is_file()
    assert not (releases / "current_release.json").exists()
    with pytest.raises(FileExistsError):
        ReleaseTransaction(releases, "release-1")


@pytest.mark.parametrize(
    "crash_at", ["before_rename", "after_rename_before_pointer"]
)
def test_crash_keeps_old_pointer_valid(tmp_path: Path, crash_at: str) -> None:
    releases = tmp_path / "releases"
    old_root = commit_empty_release(releases, "release-old")
    old_pointer = (releases / "current_transaction_test.json").read_bytes()
    transaction = ReleaseTransaction(releases, f"release-{crash_at}")
    transaction.log.write("即将模拟崩溃")
    with pytest.raises(SimulatedCrash):
        transaction._commit_infrastructure_test_only(
            crash_at=crash_at,
        )
    assert (releases / "current_transaction_test.json").read_bytes() == old_pointer
    assert old_root.is_dir()


def test_public_formal_commit_is_hard_rejected(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    with ReleaseTransaction(releases, "release-1") as transaction:
        with pytest.raises(RuntimeError, match="禁止正式 commit"):
            transaction.commit(
                input_fingerprint="f" * 64,
                runtime_signature={"python": "3.10"},
                settings={},
                release_artifact_paths=set(),
                approved_audit_run="audit-approved",
            )
    assert not (releases / "current_release.json").exists()


def test_cli_hard_rejects_audit_and_formal_without_side_effects(
    tmp_path: Path,
) -> None:
    del tmp_path
    import subprocess

    script = ROOT / "scripts" / "assemble_modeling_dataset.py"
    before_audits = (ROOT / "audits" / "dataset_assembly").exists()
    before_releases = (ROOT / "releases" / "dataset_assembly").exists()
    audit = subprocess.run(
        [sys.executable, str(script), "audit", "--dry-run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    formal = subprocess.run(
        [
            sys.executable,
            str(script),
            "formal",
            "--approved-audit-run",
            "audit-1",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert audit.returncode != 0 and "尚未实现" in audit.stderr
    assert formal.returncode != 0 and "硬性拒绝" in formal.stderr
    assert (ROOT / "audits" / "dataset_assembly").exists() is before_audits
    assert (ROOT / "releases" / "dataset_assembly").exists() is before_releases
