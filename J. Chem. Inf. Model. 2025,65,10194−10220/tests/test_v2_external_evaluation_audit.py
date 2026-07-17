from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts" / "audit_v2_external_evaluation.py"))


def test_v2_external_audit_complete_mode_verifies_the_one_shot_result() -> None:
    metadata, results = MODULE["complete_checks"]()
    assert metadata["mode"] == "COMPLETE_EXTERNAL_EVALUATION"
    assert all(passed for _, passed in results)


def test_complete_external_audit_requires_the_preregistered_controls() -> None:
    source = (ROOT / "scripts" / "audit_v2_external_evaluation.py").read_text(encoding="utf-8")
    for required in (
        "new_external_manifest_sha256",
        "connectivity_overlap_count",
        "tautomer_overlap_count",
        "created_before_external_read",
        "repeat_execution_prevented",
        "post_evaluation_model_or_policy_change",
    ):
        assert required in source
