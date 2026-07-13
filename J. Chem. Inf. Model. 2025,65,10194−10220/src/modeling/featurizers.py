"""确定性的 RDKit 结构特征；输入只是一组 SMILES 文本。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy import sparse
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, MACCSkeys, rdMolDescriptors

from .feature_registry import FeatureSpec, resolve_feature_specs


PHYSICOCHEMICAL_DESCRIPTORS = (
    ("MolWt", Descriptors.MolWt),
    ("MolLogP", Descriptors.MolLogP),
    ("MolMR", Descriptors.MolMR),
    ("TPSA", rdMolDescriptors.CalcTPSA),
    ("NumHDonors", rdMolDescriptors.CalcNumHBD),
    ("NumHAcceptors", rdMolDescriptors.CalcNumHBA),
    ("NumRotatableBonds", rdMolDescriptors.CalcNumRotatableBonds),
    ("FractionCSP3", rdMolDescriptors.CalcFractionCSP3),
    ("RingCount", rdMolDescriptors.CalcNumRings),
    ("HeavyAtomCount", Descriptors.HeavyAtomCount),
)
RDKIT_DESCRIPTORS = tuple(Descriptors._descList)


@dataclass(frozen=True)
class FeatureMatrix:
    values: np.ndarray | sparse.csr_matrix
    feature_names: tuple[str, ...]
    specs: tuple[FeatureSpec, ...]
    binary_indices: tuple[int, ...]
    descriptor_indices: tuple[int, ...]


def _molecule(smiles: str) -> Chem.Mol:
    if not isinstance(smiles, str) or not smiles:
        raise ValueError("结构特征要求非空 SMILES")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"无法解析 SMILES：{smiles!r}")
    return mol


def _finite(
    values: Iterable[float], feature_group: str, *, allow_nan: bool = False
) -> list[float]:
    result = [float(value) for value in values]
    if np.isinf(result).any() or (not allow_nan and np.isnan(result).any()):
        raise ValueError(f"{feature_group} 产生禁止的 NaN 或 Infinity")
    return result


def _one_feature_group(mol: Chem.Mol, spec: FeatureSpec) -> tuple[list[float], list[str]]:
    if spec.name == "ecfp4":
        bits = AllChem.GetMorganFingerprintAsBitVect(
            mol, radius=2, nBits=spec.n_bits, useChirality=True, useBondTypes=True
        )
        return [float(bit) for bit in bits], [f"ecfp4_{i}" for i in range(spec.n_bits or 0)]
    if spec.name == "maccs":
        bits = MACCSkeys.GenMACCSKeys(mol)
        return [float(bit) for bit in bits], [f"maccs_{i}" for i in range(len(bits))]
    if spec.name == "rdkit_descriptors":
        # 少数无机/金属结构会令部分 RDKit 连续 descriptor 为 NaN；将其保留，
        # 由只在训练折 fit 的 SimpleImputer 处理，绝不能在特征化阶段删除样本。
        return _finite(
            (fn(mol) for _, fn in RDKIT_DESCRIPTORS), spec.name, allow_nan=True
        ), [
            f"rdkit_{name}" for name, _ in RDKIT_DESCRIPTORS
        ]
    if spec.name == "physicochemical":
        return _finite((fn(mol) for _, fn in PHYSICOCHEMICAL_DESCRIPTORS), spec.name), [
            f"physchem_{name}" for name, _ in PHYSICOCHEMICAL_DESCRIPTORS
        ]
    raise AssertionError(f"缺少特征组实现：{spec.name}")


def featurize_smiles(
    smiles: Iterable[str], feature_sets: tuple[str, ...] | list[str]
) -> FeatureMatrix:
    """从 SMILES 生成特征矩阵，不接受完整 row，从接口上隔离泄漏字段。"""

    specs = resolve_feature_specs(feature_sets)
    rows: list[list[float]] = []
    names: list[str] | None = None
    for smiles_value in smiles:
        values: list[float] = []
        row_names: list[str] = []
        mol = _molecule(smiles_value)
        for spec in specs:
            group_values, group_names = _one_feature_group(mol, spec)
            values.extend(group_values)
            row_names.extend(group_names)
        if names is None:
            names = row_names
        elif names != row_names:
            raise AssertionError("相同 feature spec 的列不稳定")
        rows.append(values)
    if not rows:
        raise ValueError("不能对空 split 生成特征")
    binary_indices: list[int] = []
    descriptor_indices: list[int] = []
    offset = 0
    for spec in specs:
        width = (spec.n_bits or 0) if spec.name in {"ecfp4", "maccs"} else (
            len(RDKIT_DESCRIPTORS) if spec.name == "rdkit_descriptors" else len(PHYSICOCHEMICAL_DESCRIPTORS)
        )
        indices = list(range(offset, offset + width))
        if spec.name in {"ecfp4", "maccs"}:
            binary_indices.extend(indices)
        else:
            descriptor_indices.extend(indices)
        offset += width
    dense_values = np.asarray(rows, dtype=np.float64)
    values: np.ndarray | sparse.csr_matrix = (
        sparse.csr_matrix(dense_values) if binary_indices and not descriptor_indices else dense_values
    )
    return FeatureMatrix(
        values=values,
        feature_names=tuple(names or []),
        specs=specs,
        binary_indices=tuple(binary_indices),
        descriptor_indices=tuple(descriptor_indices),
    )


def feature_manifest(matrix: FeatureMatrix) -> dict[str, object]:
    return {
        "feature_sets": [spec.name for spec in matrix.specs],
        "feature_versions": {spec.name: spec.version for spec in matrix.specs},
        "feature_count": len(matrix.feature_names),
        "feature_names": list(matrix.feature_names),
        "structure_columns": sorted({spec.structure_column for spec in matrix.specs}),
        "binary_feature_count": len(matrix.binary_indices),
        "descriptor_feature_count": len(matrix.descriptor_indices),
        "fingerprint_parameters": {
            **(
                {"ecfp4": {"radius": 2, "n_bits": 2048, "use_chirality": True, "use_bond_types": True}}
                if any(spec.name == "ecfp4" for spec in matrix.specs)
                else {}
            ),
            **(
                {"maccs": {"n_bits": 167}}
                if any(spec.name == "maccs" for spec in matrix.specs)
                else {}
            ),
        },
        "descriptor_names": {
            "rdkit_descriptors": [name for name, _ in RDKIT_DESCRIPTORS] if any(spec.name == "rdkit_descriptors" for spec in matrix.specs) else [],
            "physicochemical": [name for name, _ in PHYSICOCHEMICAL_DESCRIPTORS] if any(spec.name == "physicochemical" for spec in matrix.specs) else [],
        },
    }
