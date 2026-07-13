"""结构特征的冻结登记表；任何来源/审计字段都不能成为输入。"""

from __future__ import annotations

from dataclasses import dataclass


STRUCTURE_COLUMNS = frozenset({"canonical_smiles", "parent_smiles"})
FORBIDDEN_FEATURE_COLUMNS = frozenset(
    {
        "source_dataset",
        "dataset_role",
        "evidence_type",
        "source_record_id",
        "label_resolution_sources_json",
        "review_status",
        "leakage_status",
        "normalized_label",
        "compound_id",
        "standardized_inchikey",
        "fold_id",
    }
)


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    version: str
    structure_column: str = "canonical_smiles"
    n_bits: int | None = None

    def __post_init__(self) -> None:
        if self.structure_column not in STRUCTURE_COLUMNS:
            raise ValueError("特征只能来自 canonical_smiles 或 parent_smiles")


FEATURE_REGISTRY: dict[str, FeatureSpec] = {
    "ecfp4": FeatureSpec("ecfp4", "1", n_bits=2048),
    "maccs": FeatureSpec("maccs", "1", n_bits=167),
    "rdkit_descriptors": FeatureSpec("rdkit_descriptors", "1"),
    "physicochemical": FeatureSpec("physicochemical", "1"),
}


def resolve_feature_specs(names: tuple[str, ...] | list[str]) -> tuple[FeatureSpec, ...]:
    if not names:
        raise ValueError("至少需要一个结构特征组")
    resolved: list[FeatureSpec] = []
    for name in names:
        if name not in FEATURE_REGISTRY:
            raise ValueError(f"未注册特征组：{name}")
        if name in FORBIDDEN_FEATURE_COLUMNS:
            raise PermissionError(f"禁止将审计/来源字段作为特征：{name}")
        resolved.append(FEATURE_REGISTRY[name])
    if len({spec.name for spec in resolved}) != len(resolved):
        raise ValueError("特征组不可重复")
    return tuple(resolved)
