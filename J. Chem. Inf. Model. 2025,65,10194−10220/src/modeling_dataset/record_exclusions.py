"""来源记录级排除原因展开。"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .enums import LabelRule
from .schema_registry import SCHEMA_REGISTRY
from .validation import validate_rows


NO_STANDARDIZED_KEY = "no_standardized_key"
NO_CARCINOGENICITY_RECORD = "无致癌性试验记录"


def exclusion_reasons(record: Mapping[str, Any]) -> set[str]:
    reasons: set[str] = set()
    if record["standard_inchikey"] == "":
        reasons.add(NO_STANDARDIZED_KEY)
    frozen_reason = str(record["exclusion_reason"])
    if not record["model_structure_ok"]:
        if frozen_reason == "":
            raise ValueError(
                f"model_structure_ok=false 但无明确原因：{record['record_key']}"
            )
        parts = frozen_reason.split(";")
        if any(part == "" for part in parts):
            raise ValueError(f"排除原因含空段：{record['record_key']}")
        reasons.update(parts)
    elif frozen_reason != "":
        reasons.update(frozen_reason.split(";"))
    if record["label_rule"] == LabelRule.NONCARCINOGENICITY_ENDPOINT_ONLY.value:
        reasons.add(NO_CARCINOGENICITY_RECORD)
    forbidden = {"other", "unknown_exclusion"}
    if reasons & forbidden:
        raise ValueError(f"禁止含糊排除原因：{sorted(reasons & forbidden)}")
    return reasons


def build_record_exclusions(
    records: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    materialized = list(records)
    expected = {
        (record["record_key"], reason)
        for record in materialized
        for reason in exclusion_reasons(record)
    }
    rows = [
        {
            "record_key": record["record_key"],
            "source_dataset": record["source_dataset"],
            "source_record_id": record["source_record_id"],
            "exclusion_reason": reason,
        }
        for record in materialized
        for reason in sorted(exclusion_reasons(record))
    ]
    actual = {(row["record_key"], row["exclusion_reason"]) for row in rows}
    if actual != expected or len(rows) != len(actual):
        raise AssertionError("record exclusions 与来源事实双向集合不一致")
    validate_rows(rows, SCHEMA_REGISTRY["modeling/record_exclusions.csv"])
    return rows
