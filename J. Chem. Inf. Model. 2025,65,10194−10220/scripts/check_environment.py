"""快速失败式验证本地复现环境。"""

from __future__ import annotations

import importlib
import platform
import sys
from importlib.metadata import PackageNotFoundError, version


EXPECTED_PYTHON = (3, 10)
PACKAGES = {
    "rdkit": "rdkit",
    "numpy": "numpy",
    "pandas": "pandas",
    "sklearn": "scikit-learn",
    "lightgbm": "lightgbm",
    "tensorflow": "tensorflow",
    "keras": "keras",
    "shap": "shap",
    "streamlit": "streamlit",
}


def package_versions() -> None:
    print(f"Python：{platform.python_version()} ({platform.machine()})")
    if sys.version_info[:2] != EXPECTED_PYTHON:
        raise RuntimeError(
            f"需要 Python {EXPECTED_PYTHON[0]}.{EXPECTED_PYTHON[1]}，"
            f"当前版本为 {sys.version_info.major}.{sys.version_info.minor}。"
        )

    for module_name, distribution_name in PACKAGES.items():
        importlib.import_module(module_name)
        try:
            installed = version(distribution_name)
        except PackageNotFoundError:
            installed = "未知"
        print(f"{distribution_name}：{installed}")


def smoke_test() -> None:
    import numpy as np
    from lightgbm import LGBMClassifier
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, MACCSkeys
    from rdkit.Chem.EState import Fingerprinter
    from sklearn.ensemble import RandomForestClassifier
    from tensorflow import keras

    mol = Chem.MolFromSmiles("CCO")
    if mol is None:
        raise RuntimeError("RDKit 无法解析冒烟测试用 SMILES。")

    canonical = Chem.MolToSmiles(mol, canonical=True)
    maccs = MACCSkeys.GenMACCSKeys(mol)
    morgan = AllChem.GetMorganGenerator(radius=2, fpSize=2048).GetFingerprint(mol)
    estate = Fingerprinter.FingerprintMol(mol)[0]
    descriptor_count = len(Descriptors.CalcMolDescriptors(mol))

    assert canonical == "CCO"
    assert maccs.GetNumBits() == 167
    assert morgan.GetNumBits() == 2048
    assert len(estate) == 79
    assert descriptor_count > 200

    x = np.array([[0.0, 1.0], [1.0, 0.0], [0.1, 0.9], [0.9, 0.1]])
    y = np.array([0, 1, 0, 1])
    RandomForestClassifier(n_estimators=2, random_state=42).fit(x, y)
    LGBMClassifier(n_estimators=2, random_state=42, verbosity=-1).fit(x, y)

    model = keras.Sequential(
        [
            keras.Input(shape=(1, 2)),
            keras.layers.Bidirectional(keras.layers.LSTM(2)),
            keras.layers.Dense(1, activation="sigmoid"),
        ]
    )
    model(np.zeros((1, 1, 2), dtype=np.float32), training=False)

    print(
        "特征冒烟测试："
        f"MACCS={maccs.GetNumBits()}, Morgan={morgan.GetNumBits()}, "
        f"E-state={len(estate)}, RDKit 描述符={descriptor_count}"
    )
    print("模型冒烟测试：LightGBM、Random Forest 和 BiLSTM 通过")


if __name__ == "__main__":
    package_versions()
    smoke_test()
    print("环境检查通过。")
