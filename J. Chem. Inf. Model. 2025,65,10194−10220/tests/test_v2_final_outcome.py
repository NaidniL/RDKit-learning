from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_final_outcome_freeze_is_aggregate_only_and_preserves_partial_status() -> None:
    source = (ROOT / "scripts" / "finalize_v2_evaluation.py").read_text(encoding="utf-8")
    assert "never open external candidate rows" in source
    assert "final-consensus-v2-external-partial-v1" in source
    assert "covered sensitivity 0.625000 < preregistered minimum 0.650000" in source


def test_final_outcome_audit_checks_the_source_binding_and_mechanical_failure() -> None:
    source = (ROOT / "scripts" / "audit_v2_final_outcome.py").read_text(encoding="utf-8")
    for required in ("source_external_evaluation", "PARTIAL_SUCCESS", "Wilson interval", "no external candidate rows read"):
        assert required in source
