"""结构实体使用的锁定 RDKit 算法。"""

from __future__ import annotations

import hashlib
import importlib
from typing import Any


Chem = importlib.import_module("rdkit.Chem")
rdMolStandardize = importlib.import_module("rdkit.Chem.MolStandardize.rdMolStandardize")
MurckoScaffold = importlib.import_module("rdkit.Chem.Scaffolds.MurckoScaffold")
rdBase = importlib.import_module("rdkit.rdBase")


def parse_parent(parent_smiles: str) -> Any:
    with rdBase.BlockLogs():
        molecule = Chem.MolFromSmiles(parent_smiles)
    if molecule is None:
        raise ValueError(f"冻结 parent SMILES 无法解析：{parent_smiles!r}")
    return molecule


def standardized_inchikey(molecule: Any) -> str:
    value = str(Chem.inchi.MolToInchiKey(molecule))
    if value == "":
        raise ValueError("RDKit 未能生成 InChIKey")
    return value


def canonical_parent_smiles(molecule: Any) -> str:
    return str(Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True))


def nonisomeric_parent_smiles(molecule: Any) -> str:
    copy = Chem.Mol(molecule)
    Chem.RemoveStereochemistry(copy)
    for atom in copy.GetAtoms():
        atom.SetIsotope(0)
    return str(Chem.MolToSmiles(copy, canonical=True, isomericSmiles=False))


def tautomer_family_key(molecule: Any) -> str:
    copy = Chem.Mol(molecule)
    Chem.RemoveStereochemistry(copy)
    for atom in copy.GetAtoms():
        atom.SetIsotope(0)
    enumerator = rdMolStandardize.TautomerEnumerator()
    enumerator.SetRemoveSp3Stereo(False)
    enumerator.SetReassignStereo(True)
    with rdBase.BlockLogs():
        canonical = enumerator.Canonicalize(copy)
    smiles = str(Chem.MolToSmiles(canonical, canonical=True, isomericSmiles=False))
    return "TAU:" + hashlib.sha256(smiles.encode("utf-8")).hexdigest()


def murcko_scaffold(molecule: Any) -> str:
    scaffold = MurckoScaffold.GetScaffoldForMol(molecule)
    return str(Chem.MolToSmiles(scaffold, canonical=True, isomericSmiles=False))


def scaffold_graph_equivalent(left: str, right: str) -> bool:
    """核对骨架拓扑，容纳 RDKit 对断键端原子的隐式氢差异。"""

    if left == right:
        return True
    with rdBase.BlockLogs():
        left_mol = Chem.MolFromSmiles(left)
        right_mol = Chem.MolFromSmiles(right)
    if left_mol is None or right_mol is None:
        return False
    if (
        left_mol.GetNumAtoms() != right_mol.GetNumAtoms()
        or left_mol.GetNumBonds() != right_mol.GetNumBonds()
    ):
        return False
    return bool(
        left_mol.HasSubstructMatch(right_mol)
        or right_mol.HasSubstructMatch(left_mol)
    )


def ecfp4(molecule: Any) -> Any:
    descriptors = importlib.import_module("rdkit.Chem.rdMolDescriptors")
    generator = getattr(descriptors, "GetMorganFingerprintAsBitVect")
    return generator(
        molecule,
        radius=2,
        nBits=2048,
        useChirality=True,
        useBondTypes=True,
        useFeatures=False,
        includeRedundantEnvironments=False,
    )
