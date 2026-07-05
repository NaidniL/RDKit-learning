"""release 路径安全与符号链接防护。"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath


def validate_relative_path(value: str) -> PurePosixPath:
    """验证 manifest/pointer 中的规范相对 POSIX 路径。"""

    if not value:
        raise ValueError("相对路径不能为空")
    if "\\" in value:
        raise ValueError(f"相对路径禁止反斜杠：{value!r}")
    if value.startswith("/"):
        raise ValueError(f"禁止绝对路径：{value!r}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"相对路径包含空段、. 或 ..：{value!r}")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError(f"禁止绝对路径：{value!r}")
    return path


def reject_symlink_chain(root: Path, target: Path) -> None:
    """拒绝 root 到 target 之间已有的任一符号链接。"""

    root_absolute = root.absolute()
    target_absolute = target.absolute()
    try:
        relative = target_absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise ValueError(f"目标路径逃逸 release 根：{target}") from exc
    current = root_absolute
    if current.is_symlink():
        raise ValueError(f"release 根不能是符号链接：{current}")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"路径包含符号链接：{current}")


def secure_join(root: Path, relative_path: str, *, must_exist: bool = False) -> Path:
    """在 root 内安全解析相对路径，并拒绝 symlink。"""

    relative = validate_relative_path(relative_path)
    candidate = root.joinpath(*relative.parts)
    reject_symlink_chain(root, candidate)
    root_resolved = root.resolve(strict=root.exists())
    candidate_resolved = candidate.resolve(strict=must_exist)
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"目标路径逃逸 release 根：{relative_path!r}") from exc
    if must_exist and not candidate.exists():
        raise FileNotFoundError(f"目标文件不存在：{candidate}")
    return candidate


def fsync_directory(path: Path) -> None:
    """同步目录项。"""

    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
