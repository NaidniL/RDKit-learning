"""结构关系边的 scope、多关系和标签比较测试。"""

from __future__ import annotations

import sys
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.structure_relations import (  # noqa: E402
    build_structure_relation_edges,
)


def _fingerprint(smiles: str):  # type: ignore[no-untyped-def]
    molecule = Chem.MolFromSmiles(smiles)
    assert molecule is not None
    return AllChem.GetMorganFingerprintAsBitVect(molecule, 2, nBits=2048)


def test_multiple_relations_and_both_cross_role_combinations() -> None:
    compound_a = "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-N"
    compound_b = "CMP:AAAAAAAAAAAAAA-CCCCCCCCCC-N"
    compounds = [
        {
            "compound_id": compound_a,
            "standardized_inchikey": compound_a.removeprefix("CMP:"),
            "connectivity_key": "AAAAAAAAAAAAAA",
            "parent_smiles": "C[C@H](O)F",
            "nonisomeric_parent_smiles": "CC(O)F",
            "tautomer_family_key": "TAU:same",
            "structure_status": "eligible",
        },
        {
            "compound_id": compound_b,
            "standardized_inchikey": compound_b.removeprefix("CMP:"),
            "connectivity_key": "AAAAAAAAAAAAAA",
            "parent_smiles": "C[C@@H](O)F",
            "nonisomeric_parent_smiles": "CC(O)F",
            "tautomer_family_key": "TAU:same",
            "structure_status": "eligible",
        },
    ]
    roles = [
        {
            "compound_id": compound_id,
            "dataset_role": role,
            "label_status": "clear_positive" if label == 1 else "clear_negative",
            "role_normalized_label": label,
        }
        for compound_id, role, label in (
            (compound_a, "development", 1),
            (compound_a, "external", 0),
            (compound_b, "development", 0),
            (compound_b, "external", 1),
        )
    ]
    fingerprints = {
        compound_a: _fingerprint("C[C@H](O)F"),
        compound_b: _fingerprint("C[C@@H](O)F"),
    }
    rows, discordant = build_structure_relation_edges(
        compounds, roles, fingerprints
    )
    relation_types = {row["relation_type"] for row in rows}
    assert relation_types == {
        "same_connectivity",
        "stereo_variant",
        "tautomer_related",
        "high_similarity",
    }
    high_similarity = [
        row for row in rows if row["relation_type"] == "high_similarity"
    ]
    assert len(high_similarity) == 4
    assert {
        (row["comparison_scope"], row["dataset_role_a"], row["dataset_role_b"])
        for row in high_similarity
    } == {
        ("development", "development", "development"),
        ("external", "external", "external"),
        ("cross_role", "development", "external"),
        ("cross_role", "external", "development"),
    }
    assert len(discordant) == 2
    assert all(row["label_relation"] == "opposite" for row in discordant)


def test_uncertain_label_is_not_comparable() -> None:
    compound_a = "CMP:AAAAAAAAAAAAAA-BBBBBBBBBB-N"
    compound_b = "CMP:DDDDDDDDDDDDDD-EEEEEEEEEE-N"
    compounds = [
        {
            "compound_id": compound_a,
            "standardized_inchikey": compound_a.removeprefix("CMP:"),
            "connectivity_key": "AAAAAAAAAAAAAA",
            "parent_smiles": "CC",
            "nonisomeric_parent_smiles": "CC",
            "tautomer_family_key": "TAU:same",
            "structure_status": "eligible",
        },
        {
            "compound_id": compound_b,
            "standardized_inchikey": compound_b.removeprefix("CMP:"),
            "connectivity_key": "DDDDDDDDDDDDDD",
            "parent_smiles": "CC",
            "nonisomeric_parent_smiles": "CC",
            "tautomer_family_key": "TAU:same",
            "structure_status": "eligible",
        },
    ]
    roles = [
        {
            "compound_id": compound_a,
            "dataset_role": "development",
            "label_status": "uncertain",
            "role_normalized_label": None,
        },
        {
            "compound_id": compound_b,
            "dataset_role": "development",
            "label_status": "clear_positive",
            "role_normalized_label": 1,
        },
    ]
    rows, _ = build_structure_relation_edges(
        compounds,
        roles,
        {compound_a: _fingerprint("CC"), compound_b: _fingerprint("CC")},
    )
    assert rows
    assert all(row["label_relation"] == "not_comparable" for row in rows)
