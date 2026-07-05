"""全数据核心重建回归和 CLI 零副作用测试。"""

from __future__ import annotations

import hashlib
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.core_pipeline import (  # noqa: E402
    EXTRA_ORTHOGONAL_CONFLICT,
    validate_core,
)
from modeling_dataset.enums import LabelStatus  # noqa: E402
from modeling_dataset.duplicate_groups import build_duplicate_groups  # noqa: E402
from modeling_dataset.role_resolution import (  # noqa: E402
    build_core_role_resolutions,
)
from modeling_dataset.schema_registry import SCHEMA_REGISTRY  # noqa: E402
from modeling_dataset.source_records import load_records_all  # noqa: E402
from modeling_dataset.validation import validate_rows  # noqa: E402


def _guarded_snapshot() -> dict[str, str]:
    roots = [
        ROOT / "audits" / "dataset_assembly",
        ROOT / "releases" / "dataset_assembly",
        ROOT / "data" / "modeling",
        ROOT / "data" / "splits",
        ROOT / "reports" / "dataset_assembly",
    ]
    snapshot: dict[str, str] = {}
    for guarded_root in roots:
        if not guarded_root.exists():
            snapshot[str(guarded_root)] = "missing"
            continue
        for path in sorted(guarded_root.rglob("*")):
            relative = path.relative_to(ROOT).as_posix()
            snapshot[relative] = (
                hashlib.sha256(path.read_bytes()).hexdigest()
                if path.is_file()
                else "directory"
            )
    return snapshot


def test_records_and_roles_full_frozen_regression() -> None:
    records = load_records_all(ROOT)
    validate_rows(records, SCHEMA_REGISTRY["modeling/records_all.csv"])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["standard_inchikey"] != "":
            grouped[record["standard_inchikey"]].append(record)
    with (
        ROOT / "data" / "processed" / "structure_representation_conflict.csv"
    ).open(encoding="utf-8", newline="") as handle:
        structure_conflicts = {
            row["standard_inchikey"] for row in csv.DictReader(handle)
        }
    compounds = [
        {
            "compound_id": f"CMP:{key}",
            "structure_status": (
                "ineligible"
                if key in structure_conflicts
                or not any(record["model_structure_ok"] for record in group)
                else "eligible"
            ),
            "structure_reasons_json": (
                ["structure_representation_conflict"]
                if key in structure_conflicts
                else []
            ),
        }
        for key, group in grouped.items()
    ]
    resolutions = build_core_role_resolutions(records, compounds)
    duplicate_groups = build_duplicate_groups(resolutions)
    assert len(records) == 38686
    assert len(grouped) == 8267
    assert len(resolutions) == 9387
    assert len(duplicate_groups) == 9387
    assert sum(item.endpoint_only for item in resolutions) == 6484
    assert Counter(item.label_status for item in resolutions) == {
        LabelStatus.CLEAR_POSITIVE: 937,
        LabelStatus.CLEAR_NEGATIVE: 956,
        LabelStatus.CONFLICT: 614,
        LabelStatus.UNCERTAIN: 6880,
    }
    resolution_map = {
        (item.compound_id, item.dataset_role.value): item for item in resolutions
    }
    extra = resolution_map[EXTRA_ORTHOGONAL_CONFLICT]
    assert extra.label_status is LabelStatus.CONFLICT
    assert extra.structure_status == "ineligible"


def test_validate_core_full_regression_without_side_effects() -> None:
    before = _guarded_snapshot()
    result = validate_core(ROOT)
    assert _guarded_snapshot() == before
    assert result.summary["status"] == "validated_core"
    assert result.summary["records_all"] == 38686
    assert result.summary["compound_count"] == 8267
    assert result.summary["conflict_count"] == 614
    assert len(result.fingerprints) == result.summary["structure_eligible_count"]
    assert len(result.review_candidates) == 614
