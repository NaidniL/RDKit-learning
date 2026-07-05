"""阶段 2 输入指纹收集与冻结输入验证。"""

from __future__ import annotations

import csv
import hashlib
import importlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from .serialization import canonical_json, digest_file


POLICY_SHA256 = "11fc682604a1f9abef1fcca09f41050b482544869a86521d556355acf694c2c5"
POLICY_PATH = "docs/modeling_dataset_policy.md"
POLICY_SHA_PATH = "docs/modeling_dataset_policy.sha256"
CLEANING_MANIFEST_PATH = "reports/cleaning/current/cleaning_manifest.json"
MANUAL_CONFLICT_PATH = "data/manual/modeling_conflict_decisions.csv"
CLEANING_TAG = "dataset-cleaning-v1.2"
CLEANING_TAG_COMMIT = "69f12496d98aee334f955893cf102b53d70aa0cd"
CLEANING_RUN_ID = "20260705_154614_567321_UTC_444f5190"
CLEANING_AUDIT_RUN_ID = "20260705_135742_751888_UTC_444f5190"
CLEANING_INPUT_FINGERPRINT = (
    "444f5190c91d070f1a9c469d1db6aef7f93ce9a2c6228f1487d021d7cc42f248"
)
CLEANING_MANIFEST_SHA256 = (
    "dca356d456167dae5424a6b6b240263c11caea2d33564a8a9d600b9da239da2f"
)
CLEANING_SETTINGS = {
    "split_method": "random",
    "validation_size": 0.2,
    "random_seed": 42,
}

FIXED_ASSEMBLY_PARAMETERS: dict[str, Any] = {
    "primary_split": {
        "method": "train_test_split",
        "validation_size": 0.2,
        "random_seed": 42,
        "stratified": True,
    },
    "cross_validation": {
        "folds": 5,
        "shuffle": True,
        "random_seed": 42,
        "scaffold_score": "exact_fraction",
    },
    "ecfp4": {
        "radius": 2,
        "n_bits": 2048,
        "use_chirality": True,
        "use_bond_types": True,
        "use_features": False,
        "include_redundant_environments": False,
        "similarity_threshold": 0.85,
    },
    "tautomer": {
        "remove_sp3_stereo": False,
        "reassign_stereo": True,
    },
    "scaffold": {
        "remove_stereochemistry": True,
        "isomeric_smiles": False,
    },
    "statistics": {
        "ddof": 0,
        "quantile_method": "linear",
        "smd_formula": "pooled_population_variance",
        "ks_alternative": "two-sided",
        "ks_method": "exact",
        "chi2_correction": False,
        "cramers_v_correction": False,
        "source_purity_min_count": 20,
        "source_purity_warning_threshold": 0.9,
        "cramers_v_warning_threshold": 0.3,
    },
    "serialization": {
        "encoding": "utf-8",
        "bom": False,
        "line_ending": "LF",
        "delimiter": ",",
        "quotechar": '"',
        "doublequote": True,
        "quoting": "QUOTE_MINIMAL",
        "missing_value": "",
        "boolean_true": "true",
        "boolean_false": "false",
        "float_format": ".17g",
        "json_sort_keys": True,
        "json_ensure_ascii": False,
        "json_separators": [",", ":"],
        "json_allow_nan": False,
    },
    "parallelism": {"threads": 1, "processes": 1},
}

PROCESSED_FILES = (
    "conflict_set.csv",
    "development_pool.csv",
    "development_review_candidates.csv",
    "discordant_evidence_set.csv",
    "excluded_set.csv",
    "external_ccris_test.csv",
    "external_review_candidates.csv",
    "inorganic_carbon_review.csv",
    "source_records_audit.csv",
    "structure_representation_conflict.csv",
    "train.csv",
    "uncertain_set.csv",
    "validation.csv",
)

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_file_metadata(root: Path, path: Path, *, csv_rows: bool) -> dict[str, Any]:
    digest = digest_file(path, csv_rows=csv_rows)
    result: dict[str, Any] = {
        "path": path.relative_to(root).as_posix(),
        "sha256": digest.sha256,
        "bytes": digest.bytes,
    }
    if digest.rows is not None:
        result["rows"] = digest.rows
    return result


def runtime_signature() -> dict[str, str]:
    """复用清洗环境签名并补充阶段 2 的 SciPy 版本。"""

    cleaning_module = importlib.import_module("carcinogenicity.cleaning")
    cleaning_signature = cast(
        Callable[[], dict[str, str]],
        getattr(cleaning_module, "runtime_signature"),
    )
    signature = cleaning_signature()
    try:
        signature["scipy"] = importlib.metadata.version("scipy")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError("缺少指纹依赖包：scipy") from exc
    signature["python_implementation"] = platform.python_implementation()
    return signature


def _implementation_paths(root: Path) -> list[Path]:
    package_files = sorted((root / "src" / "modeling_dataset").glob("*.py"))
    test_files = sorted((root / "tests").glob("test_modeling_*.py"))
    fixed = [
        root / POLICY_PATH,
        root / POLICY_SHA_PATH,
        root / "scripts" / "assemble_modeling_dataset.py",
        root / "mypy.ini",
    ]
    fixed.extend(sorted(root.glob("requirements*.txt")))
    return sorted(
        [path for path in fixed + package_files + test_files if path.is_file()],
        key=lambda item: item.relative_to(root).as_posix(),
    )


def validate_policy_hash(root: Path) -> str:
    policy = root / POLICY_PATH
    sidecar = root / POLICY_SHA_PATH
    actual = sha256_file(policy)
    if actual != POLICY_SHA256:
        raise ValueError(
            f"策略文件 SHA-256 与代码冻结值不一致：{actual} != {POLICY_SHA256}"
        )
    if not sidecar.is_file():
        raise FileNotFoundError(f"缺少策略哈希记录：{sidecar}")
    recorded = sidecar.read_text(encoding="utf-8").split()[0]
    if recorded != actual:
        raise ValueError("策略哈希记录文件与策略实际内容不一致")
    return actual


def _load_cleaning_manifest(root: Path) -> dict[str, Any]:
    path = root / CLEANING_MANIFEST_PATH
    if sha256_file(path) != CLEANING_MANIFEST_SHA256:
        raise ValueError("正式清洗 manifest SHA-256 与冻结版本不一致")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取正式清洗 manifest：{path}") from exc
    if not isinstance(value, dict):
        raise ValueError("正式清洗 manifest 顶层必须是对象")
    if value.get("run_type") != "formal":
        raise ValueError("正式清洗 manifest 的 run_type 不是 formal")
    expected_values = {
        "run_id": CLEANING_RUN_ID,
        "approved_audit_run": CLEANING_AUDIT_RUN_ID,
        "input_fingerprint": CLEANING_INPUT_FINGERPRINT,
        "settings": CLEANING_SETTINGS,
    }
    for key, expected in expected_values.items():
        if value.get(key) != expected:
            raise ValueError(f"正式清洗 manifest 冻结字段不一致：{key}")
    recorded_runtime = value.get("runtime_signature")
    if not isinstance(recorded_runtime, dict):
        raise ValueError("正式清洗 manifest 缺少 runtime_signature")
    current_runtime = runtime_signature()
    for key, expected in recorded_runtime.items():
        if current_runtime.get(key) != expected:
            raise ValueError(f"当前环境与清洗冻结环境不一致：{key}")
    return value


def cleaning_tag_commit(root: Path) -> str:
    """验证清洗冻结标签指向固定提交。"""

    result = subprocess.run(
        ["git", "-C", str(root), "rev-list", "-n", "1", CLEANING_TAG],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"无法解析冻结标签 {CLEANING_TAG}")
    commit = result.stdout.strip()
    if commit != CLEANING_TAG_COMMIT:
        raise ValueError(
            f"{CLEANING_TAG} 指向错误提交：{commit} != {CLEANING_TAG_COMMIT}"
        )
    return commit


def validate_processed_files(root: Path) -> dict[str, dict[str, Any]]:
    """逐文件核对 13 个 processed CSV 与 cleaning manifest。"""

    manifest = _load_cleaning_manifest(root)
    output_files = manifest.get("output_files")
    if not isinstance(output_files, dict):
        raise ValueError("正式清洗 manifest 缺少 output_files")
    expected_names = set(PROCESSED_FILES)
    if set(output_files) != expected_names:
        raise ValueError("processed 文件集合与 cleaning manifest 不一致")
    processed_root = root / "data" / "processed"
    actual_names = {
        path.name
        for path in processed_root.glob("*.csv")
        if path.is_file()
    }
    if actual_names != expected_names:
        raise ValueError(
            "data/processed CSV 集合不一致；"
            f"缺少={sorted(expected_names - actual_names)}，"
            f"多出={sorted(actual_names - expected_names)}"
        )
    result: dict[str, dict[str, Any]] = {}
    for name in PROCESSED_FILES:
        path = processed_root / name
        digest = digest_file(path, csv_rows=True)
        metadata = output_files[name]
        if not isinstance(metadata, dict):
            raise ValueError(f"cleaning manifest 文件元数据非法：{name}")
        if digest.sha256 != metadata.get("sha256"):
            raise ValueError(f"processed 文件哈希不一致：{name}")
        if digest.rows != metadata.get("rows"):
            raise ValueError(f"processed 文件行数不一致：{name}")
        result[name] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": digest.sha256,
            "bytes": digest.bytes,
            "rows": digest.rows,
        }
    return result


def _manual_conflict_metadata(root: Path) -> dict[str, Any]:
    path = root / MANUAL_CONFLICT_PATH
    if not path.exists():
        return {"path": MANUAL_CONFLICT_PATH, "state": "missing"}
    if not path.is_file():
        raise ValueError("人工冲突路径存在但不是普通文件")
    return {
        "state": "present",
        **_relative_file_metadata(root, path, csv_rows=True),
    }


def build_input_descriptor(
    root: Path, *, parameters: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    policy_hash = validate_policy_hash(root)
    processed = validate_processed_files(root)
    cleaning_manifest_path = root / CLEANING_MANIFEST_PATH
    cleaning_commit = cleaning_tag_commit(root)
    implementation = [
        _relative_file_metadata(root, path, csv_rows=False)
        for path in _implementation_paths(root)
    ]
    return {
        "descriptor_version": 1,
        "policy": {"path": POLICY_PATH, "sha256": policy_hash},
        "cleaning_manifest": _relative_file_metadata(
            root, cleaning_manifest_path, csv_rows=False
        ),
        "cleaning_freeze": {
            "tag": CLEANING_TAG,
            "commit": cleaning_commit,
            "run_id": CLEANING_RUN_ID,
            "approved_audit_run": CLEANING_AUDIT_RUN_ID,
            "input_fingerprint": CLEANING_INPUT_FINGERPRINT,
            "settings": CLEANING_SETTINGS,
        },
        "processed_files": [processed[name] for name in PROCESSED_FILES],
        "manual_conflict_file": _manual_conflict_metadata(root),
        "implementation_files": implementation,
        "runtime_signature": runtime_signature(),
        "parameters": {
            "fixed": FIXED_ASSEMBLY_PARAMETERS,
            "invocation": dict(parameters or {}),
        },
    }


def input_fingerprint(
    root: Path, *, parameters: Mapping[str, Any] | None = None
) -> tuple[str, dict[str, Any]]:
    """计算与 run-id 无关的输入指纹。"""

    descriptor = build_input_descriptor(root, parameters=parameters)
    payload = canonical_json(descriptor).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), descriptor


def read_source_ids_as_strings(path: Path) -> list[str]:
    """测试辅助：不做 trim 或数值推断地读取 source_record_id。"""

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "source_record_id" not in reader.fieldnames:
            raise ValueError("CSV 缺少 source_record_id")
        return [row["source_record_id"] for row in reader]
