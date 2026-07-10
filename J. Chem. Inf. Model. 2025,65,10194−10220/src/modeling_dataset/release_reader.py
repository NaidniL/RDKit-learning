"""正式 release 的完整性验证与 external 读取锁。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .manifests import verify_current_release
from .paths import secure_join
from .schema_registry import SCHEMA_REGISTRY
from .serialization import digest_file
from .validation import read_and_validate_csv


EXTERNAL_SPLITS = {
    "splits/external_test.csv",
    "splits/external_test_tautomer_clean_sensitivity.csv",
}
TUNING_SPLITS = {
    "splits/primary_reproduction/train.csv",
    "splits/primary_reproduction/validation.csv",
    "splits/primary_reproduction/train_tuning_cv_folds.csv",
    "splits/full_development_stratified_cv_folds.csv",
    "splits/full_development_scaffold_cv_folds.csv",
}


def load_release_split(
    releases_root: Path,
    relative_path: str,
    *,
    evaluation_mode: str = "model_development",
    expected_manifest_sha256: str | None = None,
) -> list[dict[str, Any]]:
    """默认拒绝 external；最终评估必须显式锁定 manifest。"""

    if relative_path not in TUNING_SPLITS | EXTERNAL_SPLITS:
        raise ValueError(f"不允许的 split 路径：{relative_path}")
    if relative_path in EXTERNAL_SPLITS:
        if evaluation_mode != "external_final":
            raise PermissionError("external split 不得进入调参或模型选择路径")
        if expected_manifest_sha256 is None:
            raise PermissionError("external 最终评估必须提供冻结 manifest SHA-256")
    elif evaluation_mode == "external_final":
        raise ValueError("external_final 模式只允许读取 external split")

    release_root, _ = verify_current_release(releases_root)
    manifest_path = release_root / "manifest.json"
    actual_manifest_sha = digest_file(manifest_path).sha256
    if (
        expected_manifest_sha256 is not None
        and actual_manifest_sha != expected_manifest_sha256
    ):
        raise ValueError("当前 release manifest 与锁定 SHA-256 不一致")
    schema = SCHEMA_REGISTRY[relative_path]
    path = secure_join(release_root, relative_path, must_exist=True)
    return read_and_validate_csv(path, schema, formal=True)
