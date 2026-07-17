from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ntp_candidate_config_is_frozen_and_does_not_reuse_v1_external() -> None:
    source = (ROOT / "configs" / "v2_external_ntp_candidate_v1.json").read_text(encoding="utf-8")
    assert '"FROZEN_CANDIDATE_ACQUISITION_PRE_EVALUATION"' in source
    assert '"not_read_or_reused"' in source
    assert "ntp-cancer-bioassay-july2020.txt" in source


def test_ntp_candidate_audit_requires_the_three_overlap_guards_and_no_scoring() -> None:
    source = (ROOT / "scripts" / "audit_v2_external_ntp_candidate.py").read_text(encoding="utf-8")
    for required in ("candidate_exact", "candidate_connectivity", "candidate_tautomers", "not EVALUATION_DIR.exists()"):
        assert required in source
    assert "不进行推断" in source


def test_one_shot_ntp_evaluator_requires_lock_before_candidate_read() -> None:
    source = (ROOT / "scripts" / "evaluate_v2_external_ntp.py").read_text(encoding="utf-8")
    assert "EVALUATION_DIR.mkdir(parents=True)" in source
    assert source.index("EVALUATION_DIR.mkdir(parents=True)") < source.index("CANDIDATE_PATH.open")
    assert "repeat_execution_prevented" in source
