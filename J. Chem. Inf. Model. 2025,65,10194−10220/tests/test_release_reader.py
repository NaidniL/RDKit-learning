from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import modeling.dataset_release_reader as reader  # noqa: E402


def test_reader_requires_dataset_assembly_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="current_release"):
        reader.load_current_release(tmp_path)


def test_reader_uses_verified_manifest_not_a_handwritten_split_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    releases_root = tmp_path / "dataset_assembly"
    release_root = releases_root / "release-1"
    release_root.mkdir(parents=True)
    (release_root / "manifest.json").write_text("{}", encoding="utf-8")
    manifest = {"run_id": "release-1", "release_artifacts": {}}
    monkeypatch.setattr(
        reader, "verify_current_release", lambda _: (release_root, manifest)
    )
    release = reader.load_current_release(releases_root)
    assert release.release_id == "release-1"
    assert len(release.manifest_sha256) == 64
    with pytest.raises(ValueError, match="manifest"):
        release.read_csv("data/splits/v1/train.csv")
