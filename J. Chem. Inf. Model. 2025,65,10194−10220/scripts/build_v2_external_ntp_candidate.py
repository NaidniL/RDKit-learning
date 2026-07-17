#!/usr/bin/env python3
"""下载、冻结并清洗 NTP cancer-bioassay candidate external；不加载 v1 external。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.split_loader import load_train_validation_splits  # noqa: E402
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402
from modeling_dataset.structure_algorithms import (  # noqa: E402
    canonical_parent_smiles,
    parse_parent,
    standardized_inchikey,
    tautomer_family_key,
)


RAW_PATH = ROOT / "data" / "raw" / "v2_external_ntp_cancer_bioassay_july2020.tsv"
MANIFEST_PATH = ROOT / "data" / "interim" / "v2_external_ntp_acquisition_manifest.json"
OUTPUT_PATH = ROOT / "data" / "processed" / "v2_external_ntp_candidate.csv"
REPORT_PATH = ROOT / "reports" / "modeling" / "v2_external_ntp_candidate.md"
EVIDENCE_COLUMNS = (
    "NTP Level Of Evidence Male Rats",
    "NTP Level Of Evidence Female Rats",
    "NTP Level Of Evidence Male Mice",
    "NTP Level Of Evidence Female Mice",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs" / "v2_external_ntp_candidate_v1.json"
    )
    parser.add_argument(
        "--releases-root", type=Path, default=ROOT / "releases" / "dataset_assembly"
    )
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_config(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError("NTP candidate config 必须是 canonical JSON")
    if value.get("status") != "FROZEN_CANDIDATE_ACQUISITION_PRE_EVALUATION":
        raise PermissionError("NTP candidate config 未冻结")
    return value


def download_once(url: str) -> bytes:
    if RAW_PATH.exists() or MANIFEST_PATH.exists() or OUTPUT_PATH.exists():
        raise FileExistsError("NTP candidate acquisition 已存在；拒绝重下载或重建")
    request = Request(url, headers={"User-Agent": "RDkit-v2-external-candidate/1.0"})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
    if not payload.startswith(b"CASRN\tChemical Name\tDTXSID\t"):
        raise ValueError("NTP source header 不符合冻结格式")
    return payload


def decode_source(payload: bytes) -> tuple[str, str]:
    """Decode the official NTP table without silently dropping characters."""
    try:
        return payload.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        # The July 2020 file contains Windows punctuation / non-breaking spaces
        # in chemical names. Preserve those source names losslessly.
        return payload.decode("cp1252"), "cp1252"


def decision(calls: list[str]) -> tuple[int | None, str]:
    observed = {item for item in calls if item}
    if "P" in observed and "NE" not in observed:
        return 1, "NTP_P_without_NE"
    if "NE" in observed and observed <= {"NE", "NT"}:
        return 0, "NTP_all_NE_or_NT"
    return None, "NTP_uncertain_or_conflicting"


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    payload = download_once(str(config["source"]["url"]))  # type: ignore[index]
    raw_digest = sha256_bytes(payload)
    release = load_formal_release_metadata_without_external_reads(args.releases_root)
    splits = load_train_validation_splits(release)
    development = [*splits.train, *splits.validation]
    development_exact = {str(row["standardized_inchikey"]) for row in development}
    development_connectivity = {key.split("-")[0] for key in development_exact}
    development_tautomers = {
        tautomer_family_key(parse_parent(str(row["canonical_smiles"]))) for row in development
    }

    text, source_encoding = decode_source(payload)
    rows = list(csv.DictReader(text.splitlines(), delimiter="\t"))
    required = {"CASRN", "Chemical Name", "QSAR Ready SMILES", *EVIDENCE_COLUMNS}
    if not rows or not required <= set(rows[0]):
        raise ValueError("NTP source 缺少冻结字段")
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    excluded = defaultdict(int)
    for row in rows:
        label, reason = decision([str(row[column]).strip() for column in EVIDENCE_COLUMNS])
        if label is None:
            excluded[reason] += 1
            continue
        smiles = str(row["QSAR Ready SMILES"]).strip()
        try:
            molecule = parse_parent(smiles)
            canonical = canonical_parent_smiles(molecule)
            inchikey = standardized_inchikey(molecule)
            tautomer = tautomer_family_key(molecule)
        except Exception:
            excluded["invalid_qsar_ready_smiles"] += 1
            continue
        connectivity = inchikey.split("-")[0]
        if inchikey in development_exact:
            excluded["development_exact_overlap"] += 1
            continue
        if connectivity in development_connectivity:
            excluded["development_connectivity_overlap"] += 1
            continue
        if tautomer in development_tautomers:
            excluded["development_tautomer_overlap"] += 1
            continue
        grouped[inchikey].append(
            {
                "canonical_smiles": canonical,
                "casrn": str(row["CASRN"]).strip(),
                "chemical_name": str(row["Chemical Name"]).strip(),
                "connectivity_key": connectivity,
                "label": label,
                "label_reason": reason,
                "ntp_calls": [str(row[column]).strip() for column in EVIDENCE_COLUMNS],
                "standardized_inchikey": inchikey,
                "tautomer_family_key": tautomer,
            }
        )
    candidates: list[dict[str, object]] = []
    for inchikey, records in sorted(grouped.items()):
        labels = {int(record["label"]) for record in records}
        if len(labels) != 1:
            excluded["within_ntp_structure_label_conflict"] += len(records)
            continue
        first = records[0]
        candidates.append(
            {
                "candidate_id": f"NTP:{inchikey}",
                "casrn": first["casrn"],
                "chemical_name": first["chemical_name"],
                "canonical_smiles": first["canonical_smiles"],
                "standardized_inchikey": inchikey,
                "connectivity_key": first["connectivity_key"],
                "tautomer_family_key": first["tautomer_family_key"],
                "normalized_label": first["label"],
                "label_reason": first["label_reason"],
                "ntp_evidence_calls_json": json.dumps(
                    sorted({tuple(record["ntp_calls"]) for record in records}), ensure_ascii=False
                ),
                "source_record_count": len(records),
            }
        )
    if not candidates or {int(row["normalized_label"]) for row in candidates} != {0, 1}:
        raise ValueError("NTP candidate 未产生两类可用、无 development overlap 的 external")

    temporary = Path(tempfile.mkdtemp(prefix=".v2_ntp_external.", dir=RAW_PATH.parent))
    try:
        raw_temp = temporary / RAW_PATH.name
        raw_temp.write_bytes(payload)
        manifest = {
            "acquisition_manifest_version": 1,
            "candidate_id": config["candidate_id"],
            "config_sha256": sha256_bytes(args.config.read_bytes()),
            "source": config["source"],
            "raw_source_sha256": raw_digest,
            "raw_source_bytes": len(payload),
            "source_encoding": source_encoding,
            "formal_release_id": release.release_id,
            "dataset_manifest_sha256": release.manifest_sha256,
            "development_split_artifacts": {
                "train.csv": release.artifact_metadata("splits/primary_reproduction/train.csv"),
                "validation.csv": release.artifact_metadata("splits/primary_reproduction/validation.csv"),
            },
            "v1_primary_external": "not_read_or_reused",
            "external_evaluation_authorized": False,
        }
        manifest_temp = temporary / MANIFEST_PATH.name
        manifest_temp.write_bytes(canonical_json_bytes(manifest))
        output_temp = temporary / OUTPUT_PATH.name
        fieldnames = list(candidates[0])
        with output_temp.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(candidates)
        report = [
            "# v2 NTP candidate external",
            "",
            "状态：`CANDIDATE BUILT — NOT AUTHORIZED FOR EXTERNAL EVALUATION`。",
            "",
            "NTP/NICEATM 的 NTP Cancer Bioassay Chemicals 表是新的候选来源。按冻结规则只保留 P 且无 NE 的阳性、以及至少一个 NE 且其余仅 NE/NT 的阴性；随后剔除与 current formal development 的 exact、connectivity 和 tautomer 重叠。脚本不读取或复用 v1 CCRIS external。",
            "",
            "## Locked source",
            "",
            f"- URL: `{config['source']['url']}`",  # type: ignore[index]
            f"- raw SHA-256: `{raw_digest}`",
            f"- source encoding: `{source_encoding}`",
            f"- raw rows: `{len(rows)}`",
            f"- release: `{release.release_id}`",
            "",
            "## Candidate result",
            "",
            f"- candidates: `{len(candidates)}`",
            f"- carcinogen: `{sum(int(row['normalized_label']) == 1 for row in candidates)}`",
            f"- noncarcinogen: `{sum(int(row['normalized_label']) == 0 for row in candidates)}`",
            "",
            "## Exclusions",
            "",
            *[f"- {name}: `{count}`" for name, count in sorted(excluded.items())],
            "",
            "该集合仍只是候选 external。必须在后续独立授权中绑定其 manifest，并完成与 v1 external 的非复用审计后，才可进入一次性 v2 external evaluation。",
            "",
        ]
        report_temp = temporary / REPORT_PATH.name
        report_temp.write_text("\n".join(report), encoding="utf-8")
        RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        os.replace(raw_temp, RAW_PATH)
        os.replace(manifest_temp, MANIFEST_PATH)
        os.replace(output_temp, OUTPUT_PATH)
        os.replace(report_temp, REPORT_PATH)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps({"candidate_count": len(candidates), "external_evaluation_authorized": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
