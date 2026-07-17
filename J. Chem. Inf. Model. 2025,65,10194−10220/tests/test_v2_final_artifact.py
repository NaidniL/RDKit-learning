from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.v2_final_artifact import (  # noqa: E402
    MEMBER_IDS,
    V2_FINAL_ARTIFACT_FILES,
    build_training_manifest,
    member_artifact_paths,
)


def test_v2_final_artifact_file_set_is_closed_and_has_no_prediction_file() -> None:
    assert "artifact_hashes.json" in V2_FINAL_ARTIFACT_FILES
    assert "consensus_manifest.json" in V2_FINAL_ARTIFACT_FILES
    assert not any("prediction" in name or "external" in name for name in V2_FINAL_ARTIFACT_FILES)
    assert member_artifact_paths("random_forest_ecfp4") == {
        "model": "member_random_forest_ecfp4_model.pkl",
        "preprocessing": "member_random_forest_ecfp4_preprocessing.pkl",
    }


def test_v2_training_manifest_is_aggregate_only_and_requires_all_members() -> None:
    members = [
        {"id": identifier, "model_artifact": {}, "preprocessing_artifact": {}}
        for identifier in MEMBER_IDS
    ]
    manifest = build_training_manifest(
        policy_sha256="a" * 64,
        release_id="release",
        dataset_manifest_sha256="b" * 64,
        split_artifacts={"train.csv": {}, "validation.csv": {}},
        labels=np.asarray([0, 1, 0]),
        members=members,
    )
    assert manifest["external_access"] == "denied"
    assert manifest["prediction_artifact_written"] is False
    assert not ({"predictions", "metrics", "validation_results"} & set(manifest))
