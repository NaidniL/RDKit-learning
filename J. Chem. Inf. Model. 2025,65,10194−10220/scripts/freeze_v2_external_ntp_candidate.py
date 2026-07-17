#!/usr/bin/env python3
"""Bind the already acquired NTP candidate rows to immutable source/config hashes."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402


CONFIG_PATH = ROOT / "configs" / "v2_external_ntp_candidate_v1.json"
RAW_PATH = ROOT / "data" / "raw" / "v2_external_ntp_cancer_bioassay_july2020.tsv"
ACQUISITION_PATH = ROOT / "data" / "interim" / "v2_external_ntp_acquisition_manifest.json"
CANDIDATE_PATH = ROOT / "data" / "processed" / "v2_external_ntp_candidate.csv"
RELEASE_MANIFEST_PATH = ROOT / "data" / "interim" / "v2_external_ntp_candidate_release_manifest.json"


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_canonical_json(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 必须是 canonical JSON object")
    return value


def main() -> int:
    if RELEASE_MANIFEST_PATH.exists():
        raise FileExistsError("candidate release manifest 已存在；拒绝重冻结")
    config = load_canonical_json(CONFIG_PATH)
    acquisition = load_canonical_json(ACQUISITION_PATH)
    if not RAW_PATH.is_file() or not CANDIDATE_PATH.is_file():
        raise FileNotFoundError("需先完成 NTP candidate acquisition")
    if acquisition.get("raw_source_sha256") != sha256_path(RAW_PATH):
        raise ValueError("冻结 raw source hash 与 acquisition manifest 不一致")
    with CANDIDATE_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"candidate_id", "normalized_label", "standardized_inchikey", "tautomer_family_key"}
    if not rows or not required <= set(rows[0]):
        raise ValueError("candidate CSV 缺少冻结字段")
    labels = Counter(row["normalized_label"] for row in rows)
    if set(labels) != {"0", "1"}:
        raise ValueError("candidate 必须包含两类标签")
    manifest = {
        "candidate_release_manifest_version": 1,
        "candidate_id": config["candidate_id"],
        "candidate_csv": {
            "bytes": CANDIDATE_PATH.stat().st_size,
            "path": "data/processed/v2_external_ntp_candidate.csv",
            "sha256": sha256_path(CANDIDATE_PATH),
        },
        "candidate_rows": len(rows),
        "class_counts": {"carcinogen": labels["1"], "noncarcinogen": labels["0"]},
        "config_sha256": sha256_path(CONFIG_PATH),
        "external_evaluation_authorized": False,
        "raw_source": {
            "bytes": RAW_PATH.stat().st_size,
            "sha256": sha256_path(RAW_PATH),
        },
        "source_acquisition_manifest": {
            "path": "data/interim/v2_external_ntp_acquisition_manifest.json",
            "sha256": sha256_path(ACQUISITION_PATH),
        },
        "status": "FROZEN_CANDIDATE_PRE_EXTERNAL_AUTHORIZATION",
        "v1_primary_external": "not_read_or_reused",
    }
    temporary = Path(tempfile.mkdtemp(prefix=".v2_ntp_candidate_release.", dir=RELEASE_MANIFEST_PATH.parent))
    try:
        output = temporary / RELEASE_MANIFEST_PATH.name
        output.write_bytes(canonical_json_bytes(manifest))
        os.replace(output, RELEASE_MANIFEST_PATH)
    finally:
        temporary.rmdir()
    print(json.dumps({"candidate_rows": len(rows), "external_evaluation_authorized": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
