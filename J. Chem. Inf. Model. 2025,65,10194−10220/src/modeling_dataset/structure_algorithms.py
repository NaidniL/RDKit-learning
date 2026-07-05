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
    Chem.RemoveStereochemistry(scaffold)
    return str(Chem.MolToSmiles(scaffold, canonical=True, isomericSmiles=False))


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
