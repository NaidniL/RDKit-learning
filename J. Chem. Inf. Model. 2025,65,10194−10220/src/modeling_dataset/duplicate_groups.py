"""从角色解析的共享聚合结果生成 duplicate groups。"""

from __future__ import annotations

from typing import Any, Iterable

from .role_resolution import CoreRoleResolution
from .schema_registry import SCHEMA_REGISTRY
from .validation import validate_rows


def build_duplicate_groups(
    resolutions: Iterable[CoreRoleResolution],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for resolution in resolutions:
        record_keys = sorted(resolution.resolution_keys + resolution.nonresolution_keys)
        if len(record_keys) != resolution.record_count:
            raise AssertionError("duplicate group 记录数与角色解析不一致")
        rows.append(
            {
                "compound_id": resolution.compound_id,
                "dataset_role": resolution.dataset_role.value,
                "record_count": resolution.record_count,
                "record_keys_json": record_keys,
                "source_labels_json": list(resolution.source_labels),
                "clear_positive_count": resolution.clear_positive_count,
                "clear_negative_count": resolution.clear_negative_count,
                "nonbinary_count": resolution.nonbinary_count,
                "discordant_nonclear_count": resolution.discordant_nonclear_count,
                "has_discordant_nonclear_evidence": resolution.has_discordant_nonclear_evidence,
                "exact_duplicate_class": resolution.exact_duplicate_class.value,
            }
        )
    validate_rows(rows, SCHEMA_REGISTRY["modeling/duplicate_groups.csv"])
    return rows
