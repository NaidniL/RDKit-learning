#!/usr/bin/env python3
"""Independently audit the frozen NTP candidate external, without scoring it."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.dataset_release_reader import (  # noqa: E402
    load_formal_release_metadata_without_external_reads,
)
from modeling.split_loader import load_train_validation_splits  # noqa: E402
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402
from modeling_dataset.structure_algorithms import parse_parent, tautomer_family_key  # noqa: E402


CONFIG_PATH = ROOT / "configs" / "v2_external_ntp_candidate_v1.json"
RAW_PATH = ROOT / "data" / "raw" / "v2_external_ntp_cancer_bioassay_july2020.tsv"
ACQUISITION_PATH = ROOT / "data" / "interim" / "v2_external_ntp_acquisition_manifest.json"
CANDIDATE_PATH = ROOT / "data" / "processed" / "v2_external_ntp_candidate.csv"
RELEASE_MANIFEST_PATH = ROOT / "data" / "interim" / "v2_external_ntp_candidate_release_manifest.json"
EVALUATION_DIR = ROOT / "reports" / "modeling" / "v2_external_evaluation_v1"
REPORT_PATH = ROOT / "reports" / "modeling" / "v2_external_ntp_candidate_audit.md"


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 必须是 canonical JSON object")
    return value


def candidate_checks() -> tuple[dict[str, Any], list[tuple[str, bool]]]:
    config = load_canonical_json(CONFIG_PATH)
    acquisition = load_canonical_json(ACQUISITION_PATH)
    release_manifest = load_canonical_json(RELEASE_MANIFEST_PATH)
    with CANDIDATE_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    release = load_formal_release_metadata_without_external_reads(ROOT / "releases" / "dataset_assembly")
    splits = load_train_validation_splits(release)
    development = [*splits.train, *splits.validation]
    exact = {str(row["standardized_inchikey"]) for row in development}
    connectivity = {key.split("-")[0] for key in exact}
    tautomers = {tautomer_family_key(parse_parent(str(row["canonical_smiles"]))) for row in development}
    labels = Counter(row["normalized_label"] for row in rows)
    results: list[tuple[str, bool]] = []
    results.append((
        "1. 冻结配置、来源和不复用 v1 CCRIS 的边界完整",
        config.get("source", {}).get("url") == "https://ntp.niehs.nih.gov/iccvam/refsubs/ntp-cancer-bioassay-july2020.txt"
        and config.get("v1_primary_external") == "not_read_or_reused"
        and acquisition.get("v1_primary_external") == "not_read_or_reused"
        and release_manifest.get("v1_primary_external") == "not_read_or_reused",
    ))
    results.append((
        "2. raw source、acquisition manifest 和 candidate CSV hashes 均已绑定",
        acquisition.get("raw_source_sha256") == sha256_path(RAW_PATH)
        and release_manifest.get("source_acquisition_manifest", {}).get("sha256") == sha256_path(ACQUISITION_PATH)
        and release_manifest.get("candidate_csv", {}).get("sha256") == sha256_path(CANDIDATE_PATH)
        and release_manifest.get("config_sha256") == sha256_path(CONFIG_PATH),
    ))
    results.append((
        "3. candidate 标签均来自冻结的 P/no-NE 或 all-NE/NT 规则，且两类均存在",
        set(labels) == {"0", "1"}
        and all(
            (row["normalized_label"] == "1" and row["label_reason"] == "NTP_P_without_NE")
            or (row["normalized_label"] == "0" and row["label_reason"] == "NTP_all_NE_or_NT")
            for row in rows
        ),
    ))
    candidate_exact = {row["standardized_inchikey"] for row in rows}
    candidate_connectivity = {row["connectivity_key"] for row in rows}
    candidate_tautomers = {row["tautomer_family_key"] for row in rows}
    results.append((
        "4. 与 formal development 的 exact/connectivity/tautomer overlap 均为零",
        not (candidate_exact & exact)
        and not (candidate_connectivity & connectivity)
        and not (candidate_tautomers & tautomers),
    ))
    results.append((
        "5. candidate 仍未获 external evaluation 授权，且没有任何 evaluation output",
        acquisition.get("external_evaluation_authorized") is False
        and release_manifest.get("external_evaluation_authorized") is False
        and release_manifest.get("status") == "FROZEN_CANDIDATE_PRE_EXTERNAL_AUTHORIZATION"
        and not EVALUATION_DIR.exists(),
    ))
    metadata = {
        "candidate_rows": len(rows),
        "class_counts": {"carcinogen": labels["1"], "noncarcinogen": labels["0"]},
        "candidate_release_manifest_sha256": sha256_path(RELEASE_MANIFEST_PATH),
        "formal_release_id": release.release_id,
        "mode": "CANDIDATE_PRE_EXTERNAL_AUTHORIZATION",
    }
    return metadata, results


def main() -> int:
    try:
        metadata, results = candidate_checks()
    except Exception as exc:
        metadata, results = {"mode": "CANDIDATE_PRE_EXTERNAL_AUTHORIZATION"}, [(type(exc).__name__, False)]
    passed = bool(results) and all(value for _, value in results)
    lines = ["# v2 NTP candidate-external audit", "", f"状态：`{'PASS' if passed else 'FAIL'}`。", ""]
    lines.extend(["## Immutable metadata", ""])
    lines.extend(f"- {key}: `{value}`" for key, value in metadata.items())
    lines.extend(["", "## Checks", "", "| # | Check | Status |", "|---:|---|---|"])
    lines.extend(
        f"| {index} | {label} | {'PASS' if value else 'FAIL'} |"
        for index, (label, value) in enumerate(results, start=1)
    )
    lines.extend(["", "本审核读取 NTP candidate 与 development 结构标识用于重叠审计；不载入 v1 CCRIS external，不进行推断或写入预测。", ""])
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
