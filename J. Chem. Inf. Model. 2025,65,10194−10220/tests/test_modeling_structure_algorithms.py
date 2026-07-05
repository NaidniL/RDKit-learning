"""RDKit 结构派生算法测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.structure_algorithms import (  # noqa: E402
    ecfp4,
    nonisomeric_parent_smiles,
    parse_parent,
    scaffold_graph_equivalent,
    standardized_inchikey,
    tautomer_family_key,
)


def test_structure_algorithms_are_deterministic() -> None:
    molecule = parse_parent("C[C@H](O)c1ccccc1")
    assert standardized_inchikey(molecule) == "WAPNOHKVXSQRPX-ZETCQYMHSA-N"
    assert nonisomeric_parent_smiles(molecule) == "CC(O)c1ccccc1"
    assert tautomer_family_key(molecule).startswith("TAU:")
    assert ecfp4(molecule).GetNumBits() == 2048


def test_invalid_parent_fails() -> None:
    with pytest.raises(ValueError, match="无法解析"):
        parse_parent("not-a-smiles")


def test_scaffold_terminal_hydrogen_serialization_is_equivalent() -> None:
    assert scaffold_graph_equivalent(
        "[CH]=C(Cc1ccccc1)c1ccccc1",
        "C=C(Cc1ccccc1)c1ccccc1",
    )
    assert not scaffold_graph_equivalent("c1ccccc1", "c1ccncc1")
