"""唯一允许训练代码进入正式数据 release 的入口。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from modeling_dataset.manifests import load_manifest, verify_current_release
from modeling_dataset.paths import secure_join
from modeling_dataset.schema_registry import SCHEMA_REGISTRY
from modeling_dataset.serialization import canonical_json_bytes, digest_file
from modeling_dataset.validation import read_and_validate_csv


@dataclass(frozen=True)
class DatasetRelease:
    """一个已完整验证、不可绕过 manifest 读取的正式 release。"""

    releases_root: Path
    root: Path
    release_id: str
    manifest_sha256: str
    manifest: dict[str, Any]

    def artifact_metadata(self, relative_path: str) -> dict[str, Any]:
        """返回已验证 manifest 中单个 artifact 的不可变元数据副本。"""

        metadata = self.manifest["release_artifacts"].get(relative_path)
        if not isinstance(metadata, dict):
            raise ValueError(f"artifact 不在当前正式 release manifest 中：{relative_path}")
        return dict(metadata)

    def read_csv(self, relative_path: str) -> list[dict[str, Any]]:
        """只读取 manifest 注册且已由整体校验覆盖的 CSV artifact。"""

        metadata = self.artifact_metadata(relative_path)
        schema = SCHEMA_REGISTRY.get(relative_path)
        if metadata is None or schema is None:
            raise ValueError(f"artifact 不在当前正式 release manifest 中：{relative_path}")
        if schema.artifact_format.value != "csv":
            raise ValueError(f"artifact 不是 CSV：{relative_path}")
        path = secure_join(self.root, relative_path, must_exist=True)
        # 在整体 release 校验之后仍逐次核验：调用者不会因长生命周期对象绕过篡改检测。
        actual = digest_file(path, csv_rows=True)
        if (
            actual.sha256 != metadata["sha256"]
            or actual.bytes != metadata["bytes"]
            or actual.rows != metadata["rows"]
        ):
            raise ValueError(f"artifact 完整性不一致：{relative_path}")
        return read_and_validate_csv(path, schema, formal=True)


def load_current_release(releases_root: Path) -> DatasetRelease:
    """验证 pointer、manifest 与全部文件后返回正式 release。

    ``releases_root`` 必须是 ``releases/dataset_assembly``；不接受 split
    目录、``data/splits`` 或单个 CSV 路径，从 API 层禁止手写训练数据路径。
    """

    if not isinstance(releases_root, Path):
        raise TypeError("releases_root 必须是 pathlib.Path")
    if releases_root.name != "dataset_assembly":
        raise ValueError("训练只能从 releases/dataset_assembly 的 current_release.json 进入")
    release_root, manifest = verify_current_release(releases_root)
    return DatasetRelease(
        releases_root=releases_root,
        root=release_root,
        # 不在校验完成后重读可变 pointer，避免 TOCTOU 造成 release/manifest 混搭。
        release_id=manifest["run_id"],
        manifest_sha256=digest_file(release_root / "manifest.json").sha256,
        manifest=manifest,
    )


def verify_full_release_in_subprocess(releases_root: Path) -> tuple[str, str]:
    """在短生命周期进程验证全部 release，避免大审计表占用训练进程内存。"""

    source_root = Path(__file__).resolve().parents[1]
    code = (
        "import json,sys; "
        f"sys.path.insert(0,{str(source_root)!r}); "
        "from pathlib import Path; "
        "from modeling.dataset_release_reader import load_current_release; "
        f"release=load_current_release(Path({str(releases_root)!r})); "
        "print(json.dumps({'release_id':release.release_id,'manifest_sha256':release.manifest_sha256}))"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(source_root) + os.pathsep + environment.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", code],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError(f"formal release 完整性验证失败：{result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
        return str(payload["release_id"]), str(payload["manifest_sha256"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError("formal release 完整性验证未返回有效锁定信息") from exc


def load_release_after_full_verification(
    releases_root: Path, *, release_id: str, manifest_sha256: str
) -> DatasetRelease:
    """重新锁定刚完成全量校验的 pointer/manifest，并逐 split 校验实际 bytes。"""

    pointer_path = secure_join(releases_root, "current_release.json", must_exist=True)
    raw = pointer_path.read_bytes()
    try:
        pointer = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("current_release.json 无法解析") from exc
    if raw != canonical_json_bytes(pointer) or not isinstance(pointer, dict):
        raise ValueError("current_release.json 不是 canonical pointer")
    if pointer.get("release_id") != release_id or pointer.get("manifest_sha256") != manifest_sha256:
        raise ValueError("完整校验后 current release pointer 发生变化")
    expected_manifest = f"{release_id}/manifest.json"
    if pointer.get("manifest_path") != expected_manifest:
        raise ValueError("pointer manifest_path 与冻结 release_id 不一致")
    manifest_path = secure_join(releases_root, expected_manifest, must_exist=True)
    if digest_file(manifest_path).sha256 != manifest_sha256:
        raise ValueError("完整校验后 manifest SHA-256 发生变化")
    manifest = load_manifest(manifest_path)
    if manifest.get("run_id") != release_id or manifest.get("run_type") != "formal":
        raise ValueError("冻结 manifest run 信息不一致")
    return DatasetRelease(
        releases_root=releases_root,
        root=manifest_path.parent,
        release_id=release_id,
        manifest_sha256=manifest_sha256,
        manifest=manifest,
    )
