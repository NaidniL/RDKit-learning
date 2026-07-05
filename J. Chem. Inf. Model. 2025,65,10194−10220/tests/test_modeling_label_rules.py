"""来源标签规则和证据类型测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.enums import (  # noqa: E402
    EvidenceType,
    LabelRule,
    SourceDataset,
)
from modeling_dataset.evidence import derive_evidence_type  # noqa: E402
from modeling_dataset.label_rules import derive_label  # noqa: E402
from modeling_dataset.source_records import record_key  # noqa: E402


@pytest.mark.parametrize(
    ("raw", "inad", "rule", "label"),
    [
        ("+", "", LabelRule.CPDB_CLEAR_POSITIVE, 1),
        ("c", "", LabelRule.CPDB_CLEAR_POSITIVE, 1),
        ("-", "", LabelRule.CPDB_CLEAR_NEGATIVE, 0),
        ("p", "", LabelRule.NONBINARY_UNCERTAIN, None),
        ("e", "", LabelRule.NONBINARY_UNCERTAIN, None),
        ("+", "i", LabelRule.NONBINARY_UNCERTAIN, None),
    ],
)
def test_cpdb_rules(raw: str, inad: str, rule: LabelRule, label: int | None) -> None:
    decision = derive_label(
        SourceDataset.CPDB,
        label_raw=raw,
        endpoint="carcinogenicity",
        payload={"opinion": raw, "inad": inad},
    )
    assert decision.rule is rule
    assert decision.normalized_label == label


@pytest.mark.parametrize(
    ("raw", "rule", "label"),
    [
        ("A (Human carcinogen)", LabelRule.IRIS_HUMAN_POSITIVE, 1),
        ("Carcinogenic to humans", LabelRule.IRIS_HUMAN_POSITIVE, 1),
        (
            "E (Evidence of non-carcinogenicity for humans)",
            LabelRule.IRIS_HUMAN_NEGATIVE,
            0,
        ),
        ("Likely to be carcinogenic to humans", LabelRule.NONBINARY_UNCERTAIN, None),
        ("unmapped", LabelRule.NONBINARY_UNCERTAIN, None),
    ],
)
def test_iris_rules(raw: str, rule: LabelRule, label: int | None) -> None:
    decision = derive_label(
        SourceDataset.IRIS,
        label_raw=raw,
        endpoint="carcinogenicity_weight_of_evidence",
        payload={},
    )
    assert decision.rule is rule
    assert decision.normalized_label == label


@pytest.mark.parametrize(
    ("raw", "endpoint", "rule", "label"),
    [
        ("POSITIVE", "carcinogenicity", LabelRule.CCRIS_EXACT_POSITIVE, 1),
        ("NEGATIVE", "carcinogenicity", LabelRule.CCRIS_EXACT_NEGATIVE, 0),
        (
            "Positive (limited)",
            "carcinogenicity",
            LabelRule.NONBINARY_UNCERTAIN,
            None,
        ),
        (
            "",
            "noncarcinogenicity_endpoint_only",
            LabelRule.NONCARCINOGENICITY_ENDPOINT_ONLY,
            None,
        ),
    ],
)
def test_ccris_rules(
    raw: str, endpoint: str, rule: LabelRule, label: int | None
) -> None:
    decision = derive_label(
        SourceDataset.CCRIS, label_raw=raw, endpoint=endpoint, payload={}
    )
    assert decision.rule is rule
    assert decision.normalized_label == label


def test_unknown_ccris_endpoint_fails() -> None:
    with pytest.raises(ValueError, match="未知终点"):
        derive_label(
            SourceDataset.CCRIS, label_raw="", endpoint="mutagenicity", payload={}
        )


def test_source_identifier_is_not_normalized() -> None:
    values = ["00123", "123", "A:B", "A\nB"]
    keys = [record_key("cpdb", value) for value in values]
    assert len(set(keys)) == len(values)


def test_evidence_types_are_source_specific() -> None:
    assert (
        derive_evidence_type(SourceDataset.IRIS, species="human_assessment")
        is EvidenceType.HUMAN_WEIGHT_OF_EVIDENCE
    )
    assert (
        derive_evidence_type(SourceDataset.CPDB, species="r")
        is EvidenceType.ANIMAL_EXPERIMENTAL
    )
    assert (
        derive_evidence_type(SourceDataset.CCRIS, species="")
        is EvidenceType.EXPERIMENTAL_UNSPECIFIED
    )
