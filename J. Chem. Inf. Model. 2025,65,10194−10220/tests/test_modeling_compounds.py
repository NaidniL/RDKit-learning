"""化合物结构实体构建测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.compounds import (  # noqa: E402
    CONFLICT_COLUMNS,
    build_compounds,
)


ETHANOL_KEY = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


def _write_conflicts(root: Path, rows: list[list[str]] | None = None) -> None:
    path = root / "data" / "processed" / "structure_representation_conflict.csv"
    path.parent.mkdir(parents=True)
    content = [",".join(CONFLICT_COLUMNS)]
    content.extend(",".join(row) for row in rows or [])
    path.write_text("\n".join(content) + "\n", encoding="utf-8")


def _record(record_key: str, parent: str, model_ok: bool) -> dict[str, Any]:
    return {
        "record_key": record_key,
        "source_dataset": "cpdb",
        "source_record_id": record_key,
        "standard_inchikey": ETHANOL_KEY,
        "connectivity_key": ETHANOL_KEY.split("-")[0],
        "parent_smiles": parent,
        "canonical_smiles": parent,
        "murcko_scaffold": "",
        "model_structure_ok": model_ok,
    }


def test_compound_stays_eligible_with_excluded_source_record(tmp_path: Path) -> None:
    _write_conflicts(tmp_path)
    rows = [_record("r1", "CCO", True), _record("r2", "CCO", False)]
    result = build_compounds(tmp_path, rows, expected_conflict_count=0)
    assert result.rows[0]["structure_status"] == "eligible"
    assert result.rows[0]["source_record_keys_json"] == ["r1", "r2"]
    assert len(result.fingerprints) == 1


def test_undeclared_multiple_parent_variants_fail(tmp_path: Path) -> None:
    _write_conflicts(tmp_path)
    rows = [_record("r1", "CCO", True), _record("r2", "OCC", True)]
    with pytest.raises(ValueError, match="未声明"):
        build_compounds(tmp_path, rows, expected_conflict_count=0)


def test_connectivity_mismatch_fails(tmp_path: Path) -> None:
    _write_conflicts(tmp_path)
    record = _record("r1", "CCO", True)
    record["connectivity_key"] = "WRONG"
    with pytest.raises(ValueError, match="connectivity"):
        build_compounds(tmp_path, [record], expected_conflict_count=0)


def test_recalculated_inchikey_mismatch_fails(tmp_path: Path) -> None:
    _write_conflicts(tmp_path)
    record = _record("r1", "CCN", True)
    with pytest.raises(ValueError, match="重算 InChIKey"):
        build_compounds(tmp_path, [record], expected_conflict_count=0)


def test_shuffled_records_produce_same_compound_row(tmp_path: Path) -> None:
    _write_conflicts(tmp_path)
    records = [_record("r2", "CCO", False), _record("r1", "CCO", True)]
    forward = build_compounds(tmp_path, records, expected_conflict_count=0).rows
    reverse = build_compounds(
        tmp_path, list(reversed(records)), expected_conflict_count=0
    ).rows
    assert forward == reverse
