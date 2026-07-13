from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.experiment_manifest import (  # noqa: E402
    build_experiment_manifest,
    load_experiment_manifest,
    write_experiment_manifest,
)


def test_experiment_manifest_records_release_and_model_hashes(tmp_path: Path) -> None:
    digest = "a" * 64
    manifest = build_experiment_manifest(
        release_id="release-1",
        release_manifest_sha256=digest,
        config={"model": "dummy", "feature_sets": ["ecfp4"], "seed": 42},
        feature_manifest_sha256=digest,
        feature_manifest={"feature_sets": ["ecfp4"], "feature_count": 2048},
        model_artifact_sha256=digest,
        model_artifact_bytes=12,
        train_cv_metrics={"auroc": 0.5},
        validation_metrics={"auroc": 0.5},
        best_params={},
        split_artifacts={
            "splits/primary_reproduction/train.csv": {"sha256": digest, "bytes": 1, "rows": 1, "schema_version": "1.0.0"},
            "splits/primary_reproduction/validation.csv": {"sha256": digest, "bytes": 1, "rows": 1, "schema_version": "1.0.0"},
            "splits/primary_reproduction/train_tuning_cv_folds.csv": {"sha256": digest, "bytes": 1, "rows": 1, "schema_version": "1.0.0"},
        },
        data_summary={"train": {"sample_count": 1, "class_counts": {"0": 1, "1": 0}}},
        runtime_signature={"python": "3.10"},
        code_revision="a" * 40,
        validation_confusion={
            "true_negative": 1,
            "false_positive": 0,
            "false_negative": 0,
            "true_positive": 0,
        },
        validation_prediction_sha256=digest,
        validation_prediction_rows=1,
    )
    path = tmp_path / "experiment_manifest.json"
    write_experiment_manifest(path, manifest)
    loaded = load_experiment_manifest(path)
    assert loaded["release_manifest_sha256"] == digest
    assert loaded["model_artifact"]["sha256"] == digest
    assert loaded["external_access"] == "denied"
    assert loaded["validation_prediction_digest"]["artifact_written"] is False
    assert set(loaded["split_artifacts"]) == {
        "splits/primary_reproduction/train.csv",
        "splits/primary_reproduction/validation.csv",
        "splits/primary_reproduction/train_tuning_cv_folds.csv",
    }
