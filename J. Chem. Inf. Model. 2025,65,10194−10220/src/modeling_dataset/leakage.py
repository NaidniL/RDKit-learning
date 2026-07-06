"""发展集阻断集合、external 泄漏状态与跨角色互变异构体审计。"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .enums import DatasetRole, LeakageContributionType, LeakageStatus
from .role_resolution import CoreRoleResolution
from .schema_registry import SCHEMA_REGISTRY
from .serialization import canonical_json
from .source_records import record_key
from .validation import validate_rows


@dataclass(frozen=True)
class LeakageBuild:
    exact_block_keys: frozenset[str]
    connectivity_block_keys: frozenset[str]
    exact_block_rows: list[dict[str, Any]]
    connectivity_block_rows: list[dict[str, Any]]
    role_statuses: dict[tuple[str, str], LeakageStatus]
    tautomer_overlap_ids: frozenset[str]
    tautomer_overlap_rows: list[dict[str, Any]]
    primary_external_ids: frozenset[str]
    sensitivity_external_ids: frozenset[str]


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise ValueError(f"冻结 CSV 必须为 UTF-8 无 BOM、LF 换行：{path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames is None:
            raise ValueError(f"冻结 CSV 缺少表头：{path}")
        return list(reader.fieldnames), [dict(row) for row in reader]


def _development_block_rows(
    root: Path,
    records: list[Mapping[str, Any]],
    compounds: list[Mapping[str, Any]],
    resolutions: list[CoreRoleResolution],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    compounds_by_id = {str(row["compound_id"]): row for row in compounds}
    records_by_identity = {
        (str(row["source_dataset"]), str(row["source_record_id"])): row
        for row in records
    }
    records_by_role_key: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(
        list
    )
    for row in records:
        records_by_role_key[
            (str(row["dataset_role"]), str(row["standard_inchikey"]))
        ].append(row)
    development_ids = {
        item.compound_id
        for item in resolutions
        if item.dataset_role is DatasetRole.DEVELOPMENT
    }
    exact_rows: list[dict[str, Any]] = []
    connectivity_rows: list[dict[str, Any]] = []
    for item in resolutions:
        if item.dataset_role is not DatasetRole.DEVELOPMENT:
            continue
        compound = compounds_by_id[item.compound_id]
        inchikey = str(compound["standardized_inchikey"])
        connectivity = str(compound["connectivity_key"])
        role_records = records_by_role_key[
            (DatasetRole.DEVELOPMENT.value, inchikey)
        ]
        if not role_records:
            raise AssertionError(f"development role 没有来源记录：{item.compound_id}")
        for row in role_records:
            exact_rows.append(
                {
                    "standardized_inchikey": inchikey,
                    "compound_id": item.compound_id,
                    "source_dataset": row["source_dataset"],
                    "record_key": row["record_key"],
                }
            )
        for source in sorted({str(row["source_dataset"]) for row in role_records}):
            connectivity_rows.append(
                {
                    "connectivity_key": connectivity,
                    "contribution_type": LeakageContributionType.COMPOUND_ROLE.value,
                    "contributor_id": item.compound_id,
                    "source_dataset": source,
                }
            )

    _, excluded_rows = _read_csv(root / "data" / "processed" / "excluded_set.csv")
    for frozen in excluded_rows:
        if frozen.get("dataset_role") != DatasetRole.DEVELOPMENT.value:
            continue
        source = frozen.get("source", "")
        source_id = frozen.get("source_record_id", "")
        source_record = records_by_identity.get((source, source_id))
        if source_record is None:
            raise ValueError(f"excluded_set 记录无法回溯来源事实：{source}/{source_id}")
        try:
            frozen_members = json.loads(
                frozen.get("leakage_connectivity_keys_json", "")
            )
            source_members = json.loads(
                str(source_record["leakage_connectivity_keys_json"])
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"excluded_set 的 leakage key 无法解析：{source}/{source_id}"
            ) from exc
        if frozen_members != source_members:
            raise ValueError(
                f"excluded_set 的 leakage key 与来源事实不一致：{source}/{source_id}"
            )
        for connectivity in source_members:
            if connectivity == "":
                continue
            connectivity_rows.append(
                {
                    "connectivity_key": connectivity,
                    "contribution_type": LeakageContributionType.EXCLUDED_RECORD_COMPONENT.value,
                    "contributor_id": record_key(source, source_id),
                    "source_dataset": source,
                }
            )

    if {str(row["compound_id"]) for row in exact_rows} != development_ids:
        raise AssertionError("development exact 阻断集未覆盖全部 development role")
    exact_rows.sort(
        key=lambda row: (
            row["standardized_inchikey"],
            row["compound_id"],
            row["source_dataset"],
            row["record_key"],
        )
    )
    connectivity_rows.sort(
        key=lambda row: (
            row["connectivity_key"],
            row["contribution_type"],
            row["contributor_id"],
            row["source_dataset"],
        )
    )
    validate_rows(
        exact_rows, SCHEMA_REGISTRY["reports/development_exact_block_set.csv"]
    )
    validate_rows(
        connectivity_rows,
        SCHEMA_REGISTRY["reports/development_connectivity_block_set.csv"],
    )
    return exact_rows, connectivity_rows


def _primary_external_ids(
    root: Path, resolutions: list[CoreRoleResolution]
) -> frozenset[str]:
    header, rows = _read_csv(root / "data" / "processed" / "external_ccris_test.csv")
    required = {"standard_inchikey", "dataset_role", "label_binary"}
    if not required <= set(header):
        raise ValueError("external_ccris_test.csv 缺少 primary external 必要列")
    resolution_map = {
        (item.compound_id, item.dataset_role.value): item for item in resolutions
    }
    result: set[str] = set()
    for row in rows:
        if row["dataset_role"] != DatasetRole.EXTERNAL.value:
            raise ValueError("primary external 冻结视图包含非 external 记录")
        compound_id = f"CMP:{row['standard_inchikey']}"
        item = resolution_map.get((compound_id, DatasetRole.EXTERNAL.value))
        if item is None or item.role_normalized_label != int(row["label_binary"]):
            raise ValueError(f"primary external 成员或标签不一致：{compound_id}")
        if compound_id in result:
            raise ValueError(f"primary external 成员重复：{compound_id}")
        result.add(compound_id)
    return frozenset(result)


def build_leakage(
    root: Path,
    records: Iterable[Mapping[str, Any]],
    compounds: Iterable[Mapping[str, Any]],
    resolutions: Iterable[CoreRoleResolution],
) -> LeakageBuild:
    """构建全部泄漏与 tautomer 结果，不写入项目目录。"""

    record_rows = list(records)
    compound_rows = list(compounds)
    role_rows = list(resolutions)
    compound_map = {str(row["compound_id"]): row for row in compound_rows}
    exact_rows, connectivity_rows = _development_block_rows(
        root, record_rows, compound_rows, role_rows
    )
    exact_keys = frozenset(str(row["standardized_inchikey"]) for row in exact_rows)
    connectivity_keys = frozenset(
        str(row["connectivity_key"]) for row in connectivity_rows
    )
    statuses: dict[tuple[str, str], LeakageStatus] = {}
    for item in role_rows:
        key = (item.compound_id, item.dataset_role.value)
        if item.dataset_role is DatasetRole.DEVELOPMENT:
            statuses[key] = LeakageStatus.NOT_APPLICABLE
            continue
        compound = compound_map[item.compound_id]
        if compound["standardized_inchikey"] in exact_keys:
            statuses[key] = LeakageStatus.EXACT_OVERLAP
        elif compound["connectivity_key"] in connectivity_keys:
            statuses[key] = LeakageStatus.CONNECTIVITY_OVERLAP
        else:
            statuses[key] = LeakageStatus.CLEAR

    primary = _primary_external_ids(root, role_rows)
    primary_bad = {
        compound_id
        for compound_id in primary
        if statuses[(compound_id, DatasetRole.EXTERNAL.value)]
        is not LeakageStatus.CLEAR
    }
    if primary_bad:
        raise ValueError(f"primary external 与 development 阻断集重叠：{sorted(primary_bad)}")

    development_tautomers: dict[str, set[str]] = defaultdict(set)
    for item in role_rows:
        compound = compound_map[item.compound_id]
        tautomer = str(compound["tautomer_family_key"])
        if (
            item.dataset_role is DatasetRole.DEVELOPMENT
            and compound["structure_status"] == "eligible"
            and tautomer != ""
        ):
            development_tautomers[tautomer].add(item.compound_id)
    tautomer_rows: list[dict[str, Any]] = []
    overlap_ids: set[str] = set()
    for item in role_rows:
        if item.dataset_role is not DatasetRole.EXTERNAL:
            continue
        tautomer = str(compound_map[item.compound_id]["tautomer_family_key"])
        matches = sorted(development_tautomers.get(tautomer, set()), key=canonical_json)
        if tautomer == "" or not matches:
            continue
        overlap_ids.add(item.compound_id)
        in_primary = item.compound_id in primary
        tautomer_rows.append(
            {
                "external_compound_id": item.compound_id,
                "tautomer_family_key": tautomer,
                "development_compound_ids_json": matches,
                "in_primary_external": in_primary,
                "removed_from_tautomer_sensitivity": in_primary,
            }
        )
    tautomer_rows.sort(key=lambda row: row["external_compound_id"])
    validate_rows(
        tautomer_rows, SCHEMA_REGISTRY["reports/cross_role_tautomer_overlaps.csv"]
    )
    sensitivity = frozenset(primary - overlap_ids)
    return LeakageBuild(
        exact_block_keys=exact_keys,
        connectivity_block_keys=connectivity_keys,
        exact_block_rows=exact_rows,
        connectivity_block_rows=connectivity_rows,
        role_statuses=statuses,
        tautomer_overlap_ids=frozenset(overlap_ids),
        tautomer_overlap_rows=tautomer_rows,
        primary_external_ids=primary,
        sensitivity_external_ids=sensitivity,
    )
