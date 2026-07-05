"""按标准 InChIKey 重建结构实体。"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .fingerprint import CLEANING_RUN_ID
from .schema_registry import SCHEMA_REGISTRY
from .serialization import canonical_json
from .structure_algorithms import (
    canonical_parent_smiles,
    ecfp4,
    murcko_scaffold,
    nonisomeric_parent_smiles,
    parse_parent,
    scaffold_graph_equivalent,
    standardized_inchikey,
    tautomer_family_key,
)
from .validation import validate_rows


INCHIKEY_PATTERN = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
CONFLICT_COLUMNS = (
    "standard_inchikey",
    "connectivity_key",
    "parent_smiles_json",
    "source_json",
    "source_record_id_json",
    "record_count",
    "conflict_reason",
)


@dataclass(frozen=True)
class CompoundBuild:
    rows: list[dict[str, Any]]
    fingerprints: dict[str, Any]


def _json_string_array(value: str, *, field: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"结构冲突字段 {field} 不是有效 JSON") from exc
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise ValueError(f"结构冲突字段 {field} 必须是字符串数组")
    if parsed != sorted(set(parsed)):
        raise ValueError(f"结构冲突字段 {field} 未排序去重")
    return parsed


def load_declared_conflicts(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "data" / "processed" / "structure_representation_conflict.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames != list(CONFLICT_COLUMNS):
            raise ValueError("结构表示冲突表 schema 不一致")
        result: dict[str, dict[str, Any]] = {}
        for frozen in reader:
            key = frozen["standard_inchikey"]
            if key in result:
                raise ValueError(f"结构表示冲突键重复：{key}")
            result[key] = {
                "connectivity_key": frozen["connectivity_key"],
                "parents": _json_string_array(
                    frozen["parent_smiles_json"], field="parent_smiles_json"
                ),
                "sources": _json_string_array(frozen["source_json"], field="source_json"),
                "source_record_ids": _json_string_array(
                    frozen["source_record_id_json"], field="source_record_id_json"
                ),
                "record_count": int(frozen["record_count"]),
                "reason": frozen["conflict_reason"],
            }
    return result


def build_compounds(
    root: Path,
    records: Iterable[Mapping[str, Any]],
    *,
    expected_conflict_count: int = 4,
) -> CompoundBuild:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        if record["standard_inchikey"] != "":
            grouped[str(record["standard_inchikey"])].append(record)
    declared = load_declared_conflicts(root)
    # 先对所有唯一 parent 执行回读预检，避免在冻结输入已非法时
    # 仍执行昂贵的 tautomer/ECFP4 派生。
    molecule_cache: dict[str, Any] = {}
    for key, group in grouped.items():
        preflight_parents = {
            str(record["parent_smiles"])
            for record in group
            if record["parent_smiles"] != ""
        }
        if len(preflight_parents) == 1:
            molecule_cache[key] = parse_parent(next(iter(preflight_parents)))
    observed_multi: set[str] = set()
    rows: list[dict[str, Any]] = []
    fingerprints: dict[str, Any] = {}
    for key in sorted(grouped):
        if not INCHIKEY_PATTERN.fullmatch(key):
            raise ValueError(f"冻结 standardized InChIKey 格式非法：{key!r}")
        group = grouped[key]
        connectivity = key.split("-")[0]
        frozen_connectivity = {
            str(record["connectivity_key"])
            for record in group
            if record["connectivity_key"] != ""
        }
        if frozen_connectivity != {connectivity}:
            raise ValueError(f"化合物 {key} 的 connectivity key 不一致")
        parents = sorted(
            {str(record["parent_smiles"]) for record in group if record["parent_smiles"] != ""}
        )
        canonical_sources = sorted(
            {
                str(record["canonical_smiles"])
                for record in group
                if record["canonical_smiles"] != ""
            }
        )
        record_keys = sorted({str(record["record_key"]) for record in group})
        sources = sorted({str(record["source_dataset"]) for record in group})
        source_ids = sorted({str(record["source_record_id"]) for record in group})
        compound_id = f"CMP:{key}"
        status = "eligible"
        reasons: list[str] = []
        representative = ""
        canonical = ""
        nonisomeric = ""
        tautomer = ""
        scaffold = ""
        if len(parents) > 1:
            observed_multi.add(key)
            expected = declared.get(key)
            observed = {
                "connectivity_key": connectivity,
                "parents": parents,
                "sources": sources,
                "source_record_ids": source_ids,
                "record_count": len(group),
                "reason": "同一 standard InChIKey 对应多个 parent SMILES",
            }
            if expected != observed:
                raise ValueError(f"未声明或内容不一致的结构表示冲突：{key}")
            status = "ineligible"
            reasons.append("structure_representation_conflict")
        elif len(parents) == 0:
            if any(bool(record["model_structure_ok"]) for record in group):
                raise ValueError(f"可建模记录缺少 parent SMILES：{key}")
            status = "ineligible"
            reasons.append("missing_parent_smiles")
        else:
            representative = parents[0]
            molecule = molecule_cache[key]
            recalculated_key = standardized_inchikey(molecule)
            if recalculated_key != key:
                raise ValueError(
                    f"化合物 {key} 重算 InChIKey 不一致：{recalculated_key}"
                )
            if not any(bool(record["model_structure_ok"]) for record in group):
                status = "ineligible"
                reasons.append("no_modelable_source_record")
            else:
                canonical = canonical_parent_smiles(molecule)
                nonisomeric = nonisomeric_parent_smiles(molecule)
                tautomer = tautomer_family_key(molecule)
                recalculated_scaffold = murcko_scaffold(molecule)
                frozen_scaffolds = {
                    str(record["murcko_scaffold"])
                    for record in group
                    if record["model_structure_ok"]
                }
                if len(frozen_scaffolds) != 1:
                    raise ValueError(f"化合物 {key} 的冻结 Murcko scaffold 不唯一")
                scaffold = next(iter(frozen_scaffolds))
                if not scaffold_graph_equivalent(scaffold, recalculated_scaffold):
                    raise ValueError(f"化合物 {key} 的 Murcko scaffold 与重算值不一致")
                fingerprints[compound_id] = ecfp4(molecule)
        rows.append(
            {
                "compound_id": compound_id,
                "standardized_inchikey": key,
                "connectivity_key": connectivity,
                "canonical_smiles": canonical,
                "parent_smiles": representative if status == "eligible" else "",
                "source_canonical_smiles_json": sorted(
                    canonical_sources, key=canonical_json
                ),
                "parent_smiles_variants_json": sorted(parents, key=canonical_json),
                "nonisomeric_parent_smiles": nonisomeric,
                "tautomer_family_key": tautomer,
                "murcko_scaffold": scaffold,
                "structure_status": status,
                "structure_reasons_json": sorted(reasons),
                "source_record_keys_json": record_keys,
                "cleaning_run_id": CLEANING_RUN_ID,
            }
        )
    if observed_multi != set(declared):
        raise ValueError(
            "结构表示冲突集合不一致；"
            f"缺少={sorted(set(declared) - observed_multi)}，"
            f"新增={sorted(observed_multi - set(declared))}"
        )
    if len(declared) != expected_conflict_count:
        raise ValueError(
            f"冻结结构表示冲突数应为 {expected_conflict_count}，"
            f"实际为 {len(declared)}"
        )
    validate_rows(rows, SCHEMA_REGISTRY["modeling/compounds.csv"])
    return CompoundBuild(rows=rows, fingerprints=fingerprints)
