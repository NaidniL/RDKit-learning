"""来源事实表的无损读取与重建。"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .enums import DatasetRole, SourceDataset
from .evidence import derive_evidence_type
from .fingerprint import CLEANING_RUN_ID
from .label_rules import LabelDecision, derive_label
from .schema_registry import SOURCE_RECORD_COLUMNS
from .serialization import canonical_json, canonical_json_array


SOURCE_ROLE = {
    SourceDataset.CPDB: DatasetRole.DEVELOPMENT,
    SourceDataset.IRIS: DatasetRole.DEVELOPMENT,
    SourceDataset.CCRIS: DatasetRole.EXTERNAL,
}
DERIVED_LABEL_FIELDS = (
    "label_category",
    "label_candidate",
    "label_confidence",
    "label_reason",
)


def record_key(source: str, source_record_id: str) -> str:
    payload = canonical_json([source, source_record_id]).encode("utf-8")
    return "REC:" + hashlib.sha256(payload).hexdigest()


def _parse_bool(value: str, *, field: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError(f"冻结字段 {field} 不是 True/False：{value!r}")


def _parse_nullable_int(value: str, *, field: str) -> int | None:
    if value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"冻结字段 {field} 不是整数：{value!r}") from exc


def _load_rows(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise ValueError("来源事实 CSV 必须为 UTF-8 无 BOM、LF 换行")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames != list(SOURCE_RECORD_COLUMNS):
            raise ValueError("来源事实 CSV 列集合或列顺序不符合冻结 schema")
        return [dict(row) for row in reader]


def _parse_payload(row: Mapping[str, str]) -> Mapping[str, Any]:
    try:
        payload = json.loads(row["source_payload_json"])
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"记录 {row['source_record_id']!r} 的 source_payload_json 无法解析"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("source_payload_json 顶层必须是对象")
    return payload


def _canonical_string_array(row: Mapping[str, str], field: str) -> str:
    try:
        parsed = json.loads(row[field])
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"记录 {row['source_record_id']!r} 的 {field} 无法解析"
        ) from exc
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise ValueError(f"记录 {row['source_record_id']!r} 的 {field} 必须是字符串数组")
    canonical_order = sorted(parsed, key=canonical_json)
    if len(canonical_order) != len(set(canonical_order)):
        raise ValueError(f"记录 {row['source_record_id']!r} 的 {field} 存在重复值")
    if parsed != canonical_order:
        raise ValueError(f"记录 {row['source_record_id']!r} 的 {field} 语义顺序非法")
    return canonical_json_array(parsed)


def _assert_label_fields(row: Mapping[str, str], decision: LabelDecision) -> None:
    expected = {
        "label_category": decision.category,
        "label_candidate": decision.candidate,
        "label_confidence": decision.confidence,
        "label_reason": decision.reason,
    }
    for name in DERIVED_LABEL_FIELDS:
        if row[name] != expected[name]:
            raise ValueError(
                f"记录 {row['source_record_id']!r} 的 {name} 与重建值不一致"
            )


def load_records_all(root: Path) -> list[dict[str, Any]]:
    """重建内存 records_all，不对项目目录产生写入。"""

    path = root / "data" / "processed" / "source_records_audit.csv"
    raw_rows = _load_rows(path)
    result: list[dict[str, Any]] = []
    source_ids: set[tuple[str, str]] = set()
    record_keys: set[str] = set()
    bool_fields = {
        "rdkit_parse_ok",
        "rdkit_mol_ok",
        "uncharging_applied",
        "residual_charge",
        "tautomer_standardized",
        "inorganic_carbon_review_required",
        "model_structure_ok",
    }
    for frozen in raw_rows:
        source = SourceDataset(frozen["source"])
        source_id = frozen["source_record_id"]
        if source_id == "":
            raise ValueError("来源记录 ID 不允许为空")
        identity = (source.value, source_id)
        if identity in source_ids:
            raise ValueError(f"来源记录 ID 重复：{identity!r}")
        source_ids.add(identity)
        expected_role = SOURCE_ROLE[source]
        if frozen["dataset_role"] != expected_role.value:
            raise ValueError(f"来源与 dataset_role 映射不一致：{identity!r}")
        payload = _parse_payload(frozen)
        decision = derive_label(
            source,
            label_raw=frozen["label_raw"],
            endpoint=frozen["endpoint"],
            payload=payload,
        )
        _assert_label_fields(frozen, decision)
        key = record_key(source.value, source_id)
        if key in record_keys:
            raise ValueError(f"record_key 碰撞：{key}")
        record_keys.add(key)
        row: dict[str, Any] = dict(frozen)
        row["source_payload_json"] = canonical_json(payload)
        row["leakage_connectivity_keys_json"] = _canonical_string_array(
            frozen, "leakage_connectivity_keys_json"
        )
        for name in bool_fields:
            row[name] = _parse_bool(frozen[name], field=name)
        row["formal_charge_before"] = _parse_nullable_int(
            frozen["formal_charge_before"], field="formal_charge_before"
        )
        row["formal_charge_after"] = _parse_nullable_int(
            frozen["formal_charge_after"], field="formal_charge_after"
        )
        row.update(
            {
                "record_key": key,
                "source_dataset": source.value,
                "source_label": frozen["label_raw"],
                "normalized_label": decision.normalized_label,
                "label_rule": decision.rule.value,
                "evidence_type": derive_evidence_type(
                    source, species=frozen["species"]
                ).value,
                "cleaning_run_id": CLEANING_RUN_ID,
            }
        )
        result.append(row)
    return result
