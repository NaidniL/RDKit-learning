from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.feature_registry import resolve_feature_specs  # noqa: E402
from modeling.featurizers import featurize_smiles  # noqa: E402


def test_structure_features_are_repeatable_and_finite() -> None:
    left = featurize_smiles(["CCO", "c1ccccc1"], ("ecfp4", "maccs", "physicochemical"))
    right = featurize_smiles(["CCO", "c1ccccc1"], ("ecfp4", "maccs", "physicochemical"))
    assert left.feature_names == right.feature_names
    assert np.array_equal(left.values, right.values)
    assert np.isfinite(left.values).all()
    assert left.values.shape[1] == 2048 + 167 + 10
    assert left.binary_indices == tuple(range(2048 + 167))
    assert left.descriptor_indices == tuple(range(2048 + 167, 2048 + 167 + 10))


def test_fingerprint_only_features_remain_sparse() -> None:
    matrix = featurize_smiles(["CCO"], ("ecfp4",))
    assert sparse.isspmatrix_csr(matrix.values)


def test_rdkit_descriptor_nan_is_preserved_for_train_only_imputation() -> None:
    matrix = featurize_smiles(["C[Hg]Cl"], ("rdkit_descriptors",))
    assert np.isnan(matrix.values).any()


def test_audit_fields_cannot_be_registered_as_features() -> None:
    with pytest.raises(ValueError, match="未注册"):
        resolve_feature_specs(("source_dataset",))
    with pytest.raises(ValueError, match="无法解析"):
        featurize_smiles(["not a smiles"], ("ecfp4",))
