"""化合物在单一数据角色内的标签解析。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .enums import DatasetRole, ExactDuplicateClass, LabelStatus, ReviewStatus
from .serialization import canonical_json


@dataclass(frozen=True)
class CoreRoleResolution:
    compound_id: str
    dataset_role: DatasetRole
    role_normalized_label: int | None
    label_status: LabelStatus
    review_status: ReviewStatus
    resolution_keys: tuple[str, ...]
    nonresolution_keys: tuple[str, ...]
    resolution_sources: tuple[str, ...]
    source_labels: tuple[str, ...]
    endpoint_only: bool
    clear_positive_count: int
    clear_negative_count: int
    nonbinary_count: int
    discordant_nonclear_count: int
    has_discordant_nonclear_evidence: bool
    exact_duplicate_class: ExactDuplicateClass
    structure_status: str
    structure_reasons: tuple[str, ...]

    @property
    def record_count(self) -> int:
        return self.clear_positive_count + self.clear_negative_count + self.nonbinary_count


def duplicate_class(
    *, positive: int, negative: int, nonbinary: int
) -> ExactDuplicateClass:
    total = positive + negative + nonbinary
    if total == 1:
        return ExactDuplicateClass.SINGLE_RECORD
    if positive > 0 and negative > 0:
        return ExactDuplicateClass.MULTIPLE_CLEAR_CONFLICTING
    if (positive > 0 or negative > 0) and nonbinary > 0:
        return ExactDuplicateClass.MULTIPLE_CLEAR_WITH_NONBINARY
    if positive > 0 or negative > 0:
        return ExactDuplicateClass.MULTIPLE_CLEAR_SAME_LABEL
    return ExactDuplicateClass.MULTIPLE_NONBINARY_ONLY


def _resolve_group(
    compound_id: str,
    role: DatasetRole,
    group: list[Mapping[str, Any]],
    compound: Mapping[str, Any],
) -> CoreRoleResolution:
    expected_sources = {"cpdb", "iris"} if role is DatasetRole.DEVELOPMENT else {"ccris"}
    actual_sources = {str(record["source_dataset"]) for record in group}
    if not actual_sources <= expected_sources:
        raise ValueError(f"角色内混入非法来源：{compound_id} {role.value}")
    positive_records = [record for record in group if record["normalized_label"] == 1]
    negative_records = [record for record in group if record["normalized_label"] == 0]
    resolution = positive_records + negative_records
    nonresolution = [record for record in group if record["normalized_label"] is None]
    if positive_records and negative_records:
        status = LabelStatus.CONFLICT
        normalized_label = None
    elif positive_records:
        status = LabelStatus.CLEAR_POSITIVE
        normalized_label = 1
    elif negative_records:
        status = LabelStatus.CLEAR_NEGATIVE
        normalized_label = 0
    else:
        status = LabelStatus.UNCERTAIN
        normalized_label = None
    discordant = 0
    if status in {LabelStatus.CLEAR_POSITIVE, LabelStatus.CLEAR_NEGATIVE}:
        opposite = "negative" if normalized_label == 1 else "positive"
        discordant = sum(
            record["label_candidate"] == opposite for record in nonresolution
        )
    review = ReviewStatus.PENDING if status is LabelStatus.CONFLICT else ReviewStatus.NOT_REQUIRED
    resolution_keys = tuple(sorted(str(record["record_key"]) for record in resolution))
    nonresolution_keys = tuple(
        sorted(str(record["record_key"]) for record in nonresolution)
    )
    all_keys = {str(record["record_key"]) for record in group}
    if set(resolution_keys) & set(nonresolution_keys):
        raise AssertionError("解析键与非解析键重叠")
    if set(resolution_keys) | set(nonresolution_keys) != all_keys:
        raise AssertionError("解析键分区未覆盖全部来源记录")
    return CoreRoleResolution(
        compound_id=compound_id,
        dataset_role=role,
        role_normalized_label=normalized_label,
        label_status=status,
        review_status=review,
        resolution_keys=resolution_keys,
        nonresolution_keys=nonresolution_keys,
        resolution_sources=tuple(
            sorted({str(record["source_dataset"]) for record in resolution})
        ),
        source_labels=tuple(
            sorted(
                {
                    str(record.get("source_label", record.get("label_candidate", "")))
                    for record in group
                }
                - {""},
                key=canonical_json,
            )
        ),
        endpoint_only=all(
            record["label_rule"] == "noncarcinogenicity_endpoint_only"
            for record in group
        ),
        clear_positive_count=len(positive_records),
        clear_negative_count=len(negative_records),
        nonbinary_count=len(nonresolution),
        discordant_nonclear_count=discordant,
        has_discordant_nonclear_evidence=discordant > 0,
        exact_duplicate_class=duplicate_class(
            positive=len(positive_records),
            negative=len(negative_records),
            nonbinary=len(nonresolution),
        ),
        structure_status=str(compound["structure_status"]),
        structure_reasons=tuple(compound["structure_reasons_json"]),
    )


def build_core_role_resolutions(
    records: Iterable[Mapping[str, Any]], compounds: Iterable[Mapping[str, Any]]
) -> list[CoreRoleResolution]:
    compound_map = {str(row["compound_id"]): row for row in compounds}
    grouped: dict[tuple[str, DatasetRole], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        key = str(record["standard_inchikey"])
        if key == "":
            continue
        compound_id = f"CMP:{key}"
        role = DatasetRole(str(record["dataset_role"]))
        grouped[(compound_id, role)].append(record)
    return [
        _resolve_group(compound_id, role, grouped[(compound_id, role)], compound_map[compound_id])
        for compound_id, role in sorted(
            grouped, key=lambda item: (item[0], 0 if item[1] is DatasetRole.DEVELOPMENT else 1)
        )
    ]
