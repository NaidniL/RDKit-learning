"""输入指纹与冻结 processed 文件验证测试。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.fingerprint import (  # noqa: E402
    CLEANING_AUDIT_RUN_ID,
    CLEANING_INPUT_FINGERPRINT,
    CLEANING_RUN_ID,
    CLEANING_SETTINGS,
    CLEANING_TAG_COMMIT,
    POLICY_PATH,
    POLICY_SHA_PATH,
    PROCESSED_FILES,
    input_fingerprint,
    cleaning_tag_commit,
    read_source_ids_as_strings,
    runtime_signature,
    validate_processed_files,
)
from modeling_dataset.serialization import canonical_json, digest_bytes  # noqa: E402


def build_fake_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    (root / "docs").mkdir(parents=True)
    (root / "data" / "processed").mkdir(parents=True)
    (root / "reports" / "cleaning" / "current").mkdir(parents=True)
    (root / "scripts").mkdir()
    source_policy = ROOT / POLICY_PATH
    (root / POLICY_PATH).write_bytes(source_policy.read_bytes())
    (root / POLICY_SHA_PATH).write_text(
        (ROOT / POLICY_SHA_PATH).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "scripts" / "assemble_modeling_dataset.py").write_text(
        "# 固定测试入口\n", encoding="utf-8"
    )
    output_files: dict[str, dict[str, object]] = {}
    for index, name in enumerate(PROCESSED_FILES):
        payload = f"id,value\n{index},值{index}\n".encode("utf-8")
        path = root / "data" / "processed" / name
        path.write_bytes(payload)
        output_files[name] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "rows": 1,
        }
    manifest = {
        "run_type": "formal",
        "run_id": CLEANING_RUN_ID,
        "approved_audit_run": CLEANING_AUDIT_RUN_ID,
        "input_fingerprint": CLEANING_INPUT_FINGERPRINT,
        "settings": CLEANING_SETTINGS,
        "runtime_signature": {
            key: value
            for key, value in runtime_signature().items()
            if key not in {"scipy", "python_implementation"}
        },
        "output_files": output_files,
    }
    (root / "reports" / "cleaning" / "current" / "cleaning_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    fake_manifest_path = (
        root / "reports" / "cleaning" / "current" / "cleaning_manifest.json"
    )
    monkeypatch.setattr(
        "modeling_dataset.fingerprint.CLEANING_MANIFEST_SHA256",
        hashlib.sha256(fake_manifest_path.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        "modeling_dataset.fingerprint.cleaning_tag_commit",
        lambda unused_root: CLEANING_TAG_COMMIT,
    )
    return root


def test_fingerprint_is_stable_and_independent_of_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fake_project(tmp_path, monkeypatch)
    first, first_descriptor = input_fingerprint(root, parameters={"seed": 42})
    second, second_descriptor = input_fingerprint(root, parameters={"seed": 42})
    assert first == second
    assert first_descriptor == second_descriptor
    assert "run_id" not in first_descriptor
    assert "run_id" not in first_descriptor["parameters"]["invocation"]
    assert first_descriptor["conflict_resolution"] == {
        "method": "ordered_clear_label_counts_v1",
        "total_count_max": 10,
        "count_margin_max": 10,
    }
    fixed = first_descriptor["parameters"]["fixed"]
    assert fixed["primary_split"]["random_seed"] == 42
    assert fixed["ecfp4"]["radius"] == 2
    assert fixed["parallelism"] == {"threads": 1, "processes": 1}
    assert first_descriptor["cleaning_freeze"]["commit"] == CLEANING_TAG_COMMIT


def test_fingerprint_ignores_retired_manual_conflict_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fake_project(tmp_path, monkeypatch)
    before, _ = input_fingerprint(root)
    manual = root / "data" / "manual" / "modeling_conflict_decisions.csv"
    manual.parent.mkdir()
    manual.write_text(
        "compound_id,dataset_role,decision,review_reason,reviewer,reviewed_at_utc\n",
        encoding="utf-8",
    )
    after, descriptor = input_fingerprint(root)
    assert before == after
    assert descriptor["conflict_resolution"]["method"] == "ordered_clear_label_counts_v1"


def test_processed_tampering_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fake_project(tmp_path, monkeypatch)
    validate_processed_files(root)
    target = root / "data" / "processed" / PROCESSED_FILES[0]
    target.write_text("id,value\n0,篡改\n", encoding="utf-8")
    with pytest.raises(ValueError, match="哈希不一致"):
        validate_processed_files(root)


def test_cleaning_freeze_mismatch_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fake_project(tmp_path, monkeypatch)
    path = root / "reports" / "cleaning" / "current" / "cleaning_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["run_id"] = "wrong-run"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        "modeling_dataset.fingerprint.CLEANING_MANIFEST_SHA256",
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="冻结字段不一致"):
        validate_processed_files(root)


def test_source_ids_keep_leading_zeroes(tmp_path: Path) -> None:
    path = tmp_path / "ids.csv"
    path.write_text("source_record_id\n00123\n123\n", encoding="utf-8")
    assert read_source_ids_as_strings(path) == ["00123", "123"]
    first = canonical_json(["cpdb", "00123"]).encode("utf-8")
    second = canonical_json(["cpdb", "123"]).encode("utf-8")
    assert digest_bytes(first)[0] != digest_bytes(second)[0]


def test_real_validate_inputs_command_is_read_only() -> None:
    import subprocess

    script = ROOT / "scripts" / "assemble_modeling_dataset.py"
    result = subprocess.run(
        [sys.executable, str(script), "validate-inputs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "validated"
    assert payload["processed_file_count"] == 13


def test_real_cleaning_tag_is_frozen() -> None:
    assert cleaning_tag_commit(ROOT) == CLEANING_TAG_COMMIT
