"""单一 release 根和原子 pointer 事务骨架。"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .paths import fsync_directory, secure_join
from .serialization import (
    FileDigest,
    canonical_json_bytes,
    digest_file,
    write_bytes_fsync,
)
from .validation import collect_regular_files


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class SimulatedCrash(RuntimeError):
    """仅供事务回归测试注入崩溃。"""


class SealedLog:
    """封口后拒绝追加的 UTF-8/LF 日志。"""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._handle = path.open("x", encoding="utf-8", newline="\n")
        self._sealed = False

    @property
    def sealed(self) -> bool:
        return self._sealed

    def write(self, message: str) -> None:
        if self._sealed:
            raise RuntimeError("日志已经封口，禁止继续写入")
        if "\r" in message:
            raise ValueError("日志禁止回车符 \\r")
        self._handle.write(message)
        if not message.endswith("\n"):
            self._handle.write("\n")

    def seal(self) -> FileDigest:
        if self._sealed:
            raise RuntimeError("日志已经封口")
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        self._sealed = True
        return digest_file(self.path)

    def close_unsealed(self) -> None:
        if not self._sealed and not self._handle.closed:
            self._handle.close()


def _validate_run_id(run_id: str) -> None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"run-id 格式非法：{run_id!r}")


def _fsync_tree(root: Path) -> None:
    directories = sorted(
        [path for path in root.rglob("*") if path.is_dir()],
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        fsync_directory(directory)
    fsync_directory(root)


class ReleaseTransaction:
    """构建完整 release 后只切换一个 pointer。"""

    def __init__(self, releases_root: Path, run_id: str) -> None:
        _validate_run_id(run_id)
        self.releases_root = releases_root
        self.run_id = run_id
        self.releases_root.mkdir(parents=True, exist_ok=True)
        self.final_root = self.releases_root / run_id
        if self.final_root.exists() or self.final_root.is_symlink():
            raise FileExistsError(f"release run-id 已存在：{run_id}")
        temp = tempfile.mkdtemp(
            prefix=f".{run_id}.tmp-", dir=str(self.releases_root)
        )
        self.temp_root = Path(temp)
        for directory in ("modeling", "splits", "reports"):
            (self.temp_root / directory).mkdir()
        self.log = SealedLog(self.temp_root / "formal.log")
        self._committed = False

    def write_artifact(self, relative_path: str, payload: bytes) -> Path:
        if self.log.sealed:
            raise RuntimeError("日志封口后禁止写入 artifact")
        path = secure_join(self.temp_root, relative_path)
        write_bytes_fsync(path, payload)
        return path

    def commit(
        self,
        *,
        input_fingerprint: str,
        runtime_signature: Mapping[str, str],
        settings: Mapping[str, Any],
        release_artifact_paths: set[str],
        approved_audit_run: str,
        crash_at: str | None = None,
    ) -> Path:
        del (
            input_fingerprint,
            runtime_signature,
            settings,
            release_artifact_paths,
            approved_audit_run,
            crash_at,
        )
        raise RuntimeError(
            "实现批次 1 禁止正式 commit；必须等待已验证 audit proof 接口"
        )

    def _commit_infrastructure_test_only(
        self,
        *,
        crash_at: str | None = None,
    ) -> Path:
        """仅在临时测试目录验证 rename/pointer 崩溃窗口。"""

        if self._committed:
            raise RuntimeError("事务已经提交")
        actual_before_seal = collect_regular_files(self.temp_root)
        expected_before_seal = {"formal.log"}
        if actual_before_seal != expected_before_seal:
            raise ValueError(
                "事务临时目录文件集合不一致；"
                f"缺少={sorted(expected_before_seal - actual_before_seal)}，"
                f"多出={sorted(actual_before_seal - expected_before_seal)}"
            )
        log_digest = self.log.seal()
        manifest = {
            "log_bytes": log_digest.bytes,
            "log_sha256": log_digest.sha256,
            "run_id": self.run_id,
            "transaction_harness": True,
        }
        manifest_path = self.temp_root / "transaction_manifest.json"
        write_bytes_fsync(manifest_path, canonical_json_bytes(manifest))
        manifest_digest = digest_file(manifest_path)
        _fsync_tree(self.temp_root)
        if crash_at == "before_rename":
            raise SimulatedCrash("模拟 release rename 前崩溃")
        os.rename(self.temp_root, self.final_root)
        fsync_directory(self.releases_root)
        if crash_at == "after_rename_before_pointer":
            raise SimulatedCrash("模拟 release rename 后、pointer 切换前崩溃")
        pointer = {
            "release_id": self.run_id,
            "manifest_path": f"{self.run_id}/transaction_manifest.json",
            "manifest_sha256": manifest_digest.sha256,
        }
        descriptor, pointer_temp_name = tempfile.mkstemp(
            prefix=".current_release.tmp-", dir=str(self.releases_root)
        )
        os.close(descriptor)
        pointer_temp = Path(pointer_temp_name)
        pointer_temp.unlink()
        write_bytes_fsync(pointer_temp, canonical_json_bytes(pointer))
        os.replace(
            pointer_temp,
            self.releases_root / "current_transaction_test.json",
        )
        fsync_directory(self.releases_root)
        self._committed = True
        return self.final_root

    def close(self) -> None:
        self.log.close_unsealed()

    def __enter__(self) -> "ReleaseTransaction":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
