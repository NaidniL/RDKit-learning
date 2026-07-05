"""证据类型的确定性派生。"""

from __future__ import annotations

from .enums import EvidenceType, SourceDataset


def derive_evidence_type(
    source: SourceDataset, *, species: str
) -> EvidenceType:
    if source is SourceDataset.IRIS:
        return EvidenceType.HUMAN_WEIGHT_OF_EVIDENCE
    if species != "":
        return EvidenceType.ANIMAL_EXPERIMENTAL
    return EvidenceType.EXPERIMENTAL_UNSPECIFIED
