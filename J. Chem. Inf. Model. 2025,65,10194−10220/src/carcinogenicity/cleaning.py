"""构建可审计的致癌性建模数据集。

程序不会覆盖原始来源记录。严格二分类数据集只使用明确标签；较弱证据和所有被排除记录
分别保留在审查或审计输出中。
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pandas as pd
from rdkit import Chem
from rdkit.Chem import rdinchi
from rdkit.Chem.MolStandardize import rdMolStandardize
from rdkit.Chem.Scaffolds import MurckoScaffold
from sklearn.model_selection import GroupShuffleSplit, train_test_split


POSITIVE = "positive"
NEGATIVE = "negative"
UNCERTAIN = "uncertain"
CONFLICT = "conflict"
EXCLUDED = "excluded"

IRIS_STRICT_POSITIVE = {
    "a (human carcinogen)",
    "carcinogenic to humans",
}
IRIS_STRICT_NEGATIVE = {
    "e (evidence of non-carcinogenicity for humans)",
}
IRIS_CANDIDATE_POSITIVE = {
    "b1 (probable human carcinogen - based on limited evidence of carcinogenicity in humans)",
    "b2 (probable human carcinogen - based on sufficient evidence of carcinogenicity in animals)",
    "c (possible human carcinogen)",
    "known/likely human carcinogen",
    "likely to be carcinogenic to humans",
    "suggestive evidence of carcinogenic potential",
    "suggestive evidence of carcinogenicity, but not sufficient to assess human carcinogenic potential",
}
IRIS_CANDIDATE_NEGATIVE = {
    "not likely to be carcinogenic to humans",
}
CCRIS_STRICT_RESULT_MAP = {
    "POSITIVE": POSITIVE,
    "NEGATIVE": NEGATIVE,
}
CCRIS_UNCERTAINTY_MARKERS = (
    "AMBIGUOUS",
    "EQUIVOCAL",
    "INADEQUATE",
    "INCONCLUSIVE",
    "MARGINAL",
    "NO TRUE DOSE RESPONSE",
    "NOT SIGNIFICANT",
    "P = 0.052",
    "POSSIBLE ADVERSE",
    "SOME EVIDENCE",
    "WEAK RESPONSE",
)
ACCEPTED_STRUCTURE_STATUSES = {"matched", "ok", "resolved"}
IDENTIFIER_PLACEHOLDERS = {
    "",
    "$null",
    "n/a",
    "na",
    "none",
    "not available",
    "null",
    "unknown",
    "various",
}
COMPOUND_COLUMNS = [
    "compound_id",
    "dataset_role",
    "source",
    "source_record_id",
    "casrn",
    "name",
    "raw_smiles",
    "canonical_smiles",
    "parent_smiles",
    "standard_inchikey",
    "connectivity_key",
    "murcko_scaffold",
    "label_raw",
    "label_binary",
    "label_category",
    "label_candidate",
    "label_confidence",
    "endpoint",
    "species",
    "route",
    "reference",
    "rdkit_mol_ok",
    "standardization_notes",
    "formal_charge_before",
    "formal_charge_after",
    "uncharging_applied",
    "residual_charge",
    "tautomer_standardized",
    "clear_positive_records",
    "clear_negative_records",
    "uncertain_records",
    "nonclear_disagreement",
    "external_overlap",
    "label_evidence_json",
]

KNOWN_INORGANIC_CARBON_COMPOSITIONS = {
    (6,): "元素碳或单原子碳",
    (6, 7): "氰根或氰化物",
    (6, 8): "一氧化碳",
    (6, 7, 8): "氰酸根",
    (6, 7, 16): "硫氰酸根",
    (6, 8, 8): "二氧化碳",
    (6, 8, 16): "羰基硫",
    (6, 16, 16): "二硫化碳",
    (6, 8, 8, 8): "碳酸根或碳酸氢根",
}


@dataclass(frozen=True)
class CleaningConfig:
    root: Path
    split_method: str = "random"
    validation_size: float = 0.20
    random_seed: int = 42
    dry_run: bool = False
    approved_audit_run: str = ""

    @property
    def raw_dir(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.root / "data" / "processed"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def cleaning_reports_dir(self) -> Path:
        return self.reports_dir / "cleaning"

    @property
    def manual_dir(self) -> Path:
        return self.root / "data" / "manual"

    @property
    def inorganic_carbon_decisions_path(self) -> Path:
        return self.manual_dir / "inorganic_carbon_decisions.csv"


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def require_columns(frame: pd.DataFrame, required: set[str], source: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{source}：缺少必需字段：{', '.join(missing)}")


def read_raw_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def parse_record_list(
    value: str,
    *,
    source: str,
    record_id: str,
    field: str,
) -> list[dict[str, Any]]:
    """解析并验证必须由对象列表组成的 JSON 字段。"""
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{source} 记录 {record_id} 的 {field} 不是有效 JSON：{error}"
        ) from error
    if not isinstance(parsed, list) or any(not isinstance(item, dict) for item in parsed):
        raise ValueError(
            f"{source} 记录 {record_id} 的 {field} 必须是对象列表"
        )
    return parsed


def cpdb_label(row: pd.Series) -> tuple[str, str, str, str]:
    opinion = row["opinion"].strip().lower()
    if row["inad"].strip().lower() == "i":
        return UNCERTAIN, "", "none", "实验证据不足"
    if opinion in {"+", "c"}:
        return POSITIVE, POSITIVE, "high", "明确阳性"
    if opinion == "-":
        return NEGATIVE, NEGATIVE, "high", "明确阴性"
    if opinion in {"p", "a"}:
        return UNCERTAIN, POSITIVE, "medium", "提示性阳性证据"
    if opinion == "e":
        return UNCERTAIN, "", "none", "证据不明确"
    return UNCERTAIN, "", "none", "无明确判断"


def normalize_cpdb(raw_dir: Path) -> pd.DataFrame:
    frame = read_raw_csv(raw_dir / "cpdb_raw.csv")
    require_columns(
        frame,
        {
            "idnum",
            "chemcode",
            "name",
            "cas",
            "opinion",
            "inad",
            "species",
            "route",
            "papernum",
        },
        "CPDB",
    )
    rows = []
    for record in frame.to_dict(orient="records"):
        if not record["chemcode"]:
            raise ValueError(f"CPDB 记录 {record['idnum']!r} 缺少 chemcode")
        series = pd.Series(record)
        category, candidate, confidence, reason = cpdb_label(series)
        rows.append(
            {
                "source": "cpdb",
                "dataset_role": "development",
                "source_record_id": record["idnum"],
                "source_chemical_id": record["chemcode"],
                "casrn": record["cas"],
                "name": record["name"],
                "endpoint": "carcinogenicity",
                "species": record["species"],
                "route": record["route"],
                "reference": record["papernum"],
                "label_raw": record["opinion"],
                "label_category": category,
                "label_candidate": candidate,
                "label_confidence": confidence,
                "label_reason": reason,
                "source_payload_json": json_text(record),
            }
        )
    return pd.DataFrame(rows)


def iris_label(description: str) -> tuple[str, str, str, str]:
    normalized = " ".join(description.casefold().split())
    if normalized in IRIS_STRICT_POSITIVE:
        return POSITIVE, POSITIVE, "high", "明确人类致癌物"
    if normalized in IRIS_STRICT_NEGATIVE:
        return NEGATIVE, NEGATIVE, "high", "明确人类非致癌物"
    if normalized in IRIS_CANDIDATE_POSITIVE:
        return UNCERTAIN, POSITIVE, "medium", "较弱的阳性证据权重"
    if normalized in IRIS_CANDIDATE_NEGATIVE:
        return UNCERTAIN, NEGATIVE, "medium", "存在暴露途径或剂量条件的阴性候选"
    return UNCERTAIN, "", "none", "无法二分类或证据权重不足"


def normalize_dtxsid(dtxsid: str) -> str:
    """将有效 DTXSID 规范为大写，占位值规范为空字符串。"""
    normalized_dtxsid = str(dtxsid).strip()
    if normalized_dtxsid.casefold() in IDENTIFIER_PLACEHOLDERS:
        return ""
    if not re.fullmatch(r"DTXSID\d+", normalized_dtxsid, flags=re.IGNORECASE):
        raise ValueError(f"IRIS DTXSID 格式非法：{normalized_dtxsid!r}")
    return normalized_dtxsid.upper()


def iris_chemical_id(dtxsid: str, casrn: str, name: str) -> str:
    """生成 IRIS 稳定关联键，避免 Various 等 CASRN 占位值冲突。"""
    normalized_dtxsid = normalize_dtxsid(dtxsid)
    if normalized_dtxsid:
        return normalized_dtxsid
    normalized_casrn = str(casrn).strip()
    if normalized_casrn.casefold() not in IDENTIFIER_PLACEHOLDERS:
        if not re.fullmatch(r"\d{2,7}-\d{2}-\d", normalized_casrn):
            raise ValueError(f"IRIS CASRN 格式非法：{normalized_casrn!r}")
        digits = normalized_casrn.replace("-", "")
        expected_check_digit = sum(
            multiplier * int(digit)
            for multiplier, digit in enumerate(reversed(digits[:-1]), start=1)
        ) % 10
        if expected_check_digit != int(digits[-1]):
            raise ValueError(f"IRIS CASRN 校验位错误：{normalized_casrn!r}")
        return normalized_casrn
    normalized_name = " ".join(str(name).casefold().split())
    if normalized_name in IDENTIFIER_PLACEHOLDERS:
        raise ValueError("IRIS 化学物同时缺少 DTXSID、有效 CASRN 和名称")
    name_digest = hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()[:16]
    return f"IRIS-NAME:{name_digest}"


def normalize_iris(raw_dir: Path) -> pd.DataFrame:
    frame = read_raw_csv(raw_dir / "iris_raw.csv")
    require_columns(
        frame,
        {"CHEMICAL NAME", "CASRN", "DTXSID", "WOE DETAILS JSON"},
        "IRIS",
    )
    rows = []
    for chemical in frame.to_dict(orient="records"):
        chemical_id = iris_chemical_id(
            chemical["DTXSID"], chemical["CASRN"], chemical["CHEMICAL NAME"]
        )
        details = parse_record_list(
            chemical["WOE DETAILS JSON"],
            source="IRIS",
            record_id=chemical_id,
            field="WOE DETAILS JSON",
        )
        if not details:
            details = [{}]
        for index, detail in enumerate(details, start=1):
            description = str(detail.get("WOE DESCRIPTION", ""))
            category, candidate, confidence, reason = iris_label(description)
            rows.append(
                {
                    "source": "iris",
                    "dataset_role": "development",
                    "source_record_id": f"{chemical_id}:woe:{index}",
                    "source_chemical_id": chemical_id,
                    "casrn": chemical["CASRN"],
                    "name": chemical["CHEMICAL NAME"],
                    "endpoint": "carcinogenicity_weight_of_evidence",
                    "species": "human_assessment",
                    "route": str(detail.get("ROUTE", "")),
                    "reference": str(detail.get("WOE TITLE", "")),
                    "label_raw": description,
                    "label_category": category,
                    "label_candidate": candidate,
                    "label_confidence": confidence,
                    "label_reason": reason,
                    "source_payload_json": json_text(
                        {"chemical": chemical, "woe_detail": detail}
                    ),
                }
            )
    return pd.DataFrame(rows)


def ccris_label(result: str) -> tuple[str, str, str, str]:
    normalized = " ".join(result.upper().split())
    if normalized in CCRIS_STRICT_RESULT_MAP:
        label = CCRIS_STRICT_RESULT_MAP[normalized]
        return label, label, "high", f"明确{'阳性' if label == POSITIVE else '阴性'}白名单"
    candidate = ""
    if normalized.startswith("POSITIVE"):
        candidate = POSITIVE
    elif normalized.startswith("NEGATIVE"):
        candidate = NEGATIVE
    if any(marker in normalized for marker in CCRIS_UNCERTAINTY_MARKERS):
        return UNCERTAIN, candidate, "medium" if candidate else "none", "带限制性描述的结果"
    if candidate:
        return UNCERTAIN, candidate, "medium", "未纳入严格白名单的带方向结果"
    return UNCERTAIN, "", "none", "无法映射的结果"


def normalize_ccris(raw_dir: Path) -> pd.DataFrame:
    frame = read_raw_csv(raw_dir / "ccris_raw.csv")
    require_columns(
        frame,
        {
            "DOCNO",
            "NameOfSubstance",
            "CASRegistryNumber",
            "carcinogenicity_studies_json",
        },
        "CCRIS",
    )
    rows = []
    for chemical in frame.to_dict(orient="records"):
        if not chemical["DOCNO"]:
            raise ValueError(
                f"CCRIS 化学物 {chemical['NameOfSubstance']!r} 缺少 DOCNO"
            )
        studies = parse_record_list(
            chemical["carcinogenicity_studies_json"],
            source="CCRIS",
            record_id=chemical["DOCNO"],
            field="carcinogenicity_studies_json",
        )
        if not studies:
            rows.append(
                {
                    "source": "ccris",
                    "dataset_role": "external",
                    "source_record_id": f"{chemical['DOCNO']}:no_carcinogenicity",
                    "source_chemical_id": chemical["DOCNO"],
                    "casrn": chemical["CASRegistryNumber"],
                    "name": chemical["NameOfSubstance"],
                    "endpoint": "noncarcinogenicity_endpoint_only",
                    "species": "",
                    "route": "",
                    "reference": "",
                    "label_raw": "",
                    "label_category": EXCLUDED,
                    "label_candidate": "",
                    "label_confidence": "none",
                    "label_reason": "无致癌性试验记录",
                    "source_payload_json": json_text(
                        {"DOCNO": chemical["DOCNO"], "dtyp": chemical.get("dtyp", "")}
                    ),
                }
            )
            continue
        for index, study in enumerate(studies, start=1):
            result = str(study.get("rsltc", ""))
            category, candidate, confidence, reason = ccris_label(result)
            rows.append(
                {
                    "source": "ccris",
                    "dataset_role": "external",
                    "source_record_id": f"{chemical['DOCNO']}:cstu:{index}",
                    "source_chemical_id": chemical["DOCNO"],
                    "casrn": chemical["CASRegistryNumber"],
                    "name": chemical["NameOfSubstance"],
                    "endpoint": "carcinogenicity",
                    "species": str(study.get("specc", "")),
                    "route": str(study.get("routc", "")),
                    "reference": str(study.get("ref", "")),
                    "label_raw": result,
                    "label_category": category,
                    "label_candidate": candidate,
                    "label_confidence": confidence,
                    "label_reason": reason,
                    "source_payload_json": json_text(study),
                }
            )
    return pd.DataFrame(rows)


def validate_source_record_ids(records: pd.DataFrame) -> None:
    """验证每个来源证据记录 ID 非空且在数据源内唯一。"""
    empty_id = records["source_record_id"].astype(str).str.strip().eq("")
    if empty_id.any():
        bad = records.loc[empty_id, ["source", "source_chemical_id"]]
        raise ValueError("存在空的来源记录 ID：\n" + bad.to_string(index=False))

    duplicate = records.duplicated(["source", "source_record_id"], keep=False)
    if duplicate.any():
        bad = records.loc[
            duplicate,
            [
                "source",
                "source_record_id",
                "source_chemical_id",
                "label_raw",
                "label_category",
            ],
        ].sort_values(["source", "source_record_id"])
        raise ValueError("存在重复的来源记录 ID：\n" + bad.to_string(index=False))


def is_clear_carbon_anion(fragment: Chem.Mol) -> bool:
    """仅识别图结构明确的单碳阴离子或小型乙炔化物阴离子。"""
    atoms = list(fragment.GetAtoms())
    if not atoms or len(atoms) > 2:
        return False
    if any(atom.GetAtomicNum() != 6 for atom in atoms):
        return False
    if Chem.GetFormalCharge(fragment) >= 0:
        return False
    if len(atoms) == 1:
        return atoms[0].GetTotalNumHs() == 0
    bonds = list(fragment.GetBonds())
    return (
        len(bonds) == 1
        and bonds[0].GetBondType() == Chem.BondType.TRIPLE
        and all(atom.GetTotalNumHs() == 0 for atom in atoms)
    )


def known_inorganic_carbon_reason(fragment: Chem.Mol) -> str:
    """识别明确列入表中的无机含碳片段。"""
    if is_clear_carbon_anion(fragment):
        return "碳化物或金属乙炔化物"
    carbon_atoms = [atom for atom in fragment.GetAtoms() if atom.GetAtomicNum() == 6]
    if len(carbon_atoms) != 1:
        return ""
    carbon = carbon_atoms[0]
    if carbon.GetTotalNumHs() != 0:
        return ""
    other_atoms = [atom for atom in fragment.GetAtoms() if atom.GetIdx() != carbon.GetIdx()]
    if any(fragment.GetBondBetweenAtoms(carbon.GetIdx(), atom.GetIdx()) is None for atom in other_atoms):
        return ""
    composition = tuple(sorted(atom.GetAtomicNum() for atom in fragment.GetAtoms()))
    return KNOWN_INORGANIC_CARBON_COMPOSITIONS.get(composition, "")


def requires_inorganic_carbon_review(fragment: Chem.Mol) -> bool:
    """标记未列入明确无机表的小型疑似无机含碳片段。"""
    carbon_atoms = [atom for atom in fragment.GetAtoms() if atom.GetAtomicNum() == 6]
    if not carbon_atoms:
        return False
    carbon_only_anion = all(
        atom.GetAtomicNum() == 6 for atom in fragment.GetAtoms()
    ) and Chem.GetFormalCharge(fragment) < 0
    has_carbon_carbon_bond = any(
        bond.GetBeginAtom().GetAtomicNum() == 6
        and bond.GetEndAtom().GetAtomicNum() == 6
        for bond in fragment.GetBonds()
    )
    single_carbon_small = (
        len(carbon_atoms) == 1
        and fragment.GetNumHeavyAtoms() <= 4
        and not has_carbon_carbon_bond
    )
    has_carbon_hydrogen = any(atom.GetTotalNumHs() > 0 for atom in carbon_atoms)
    allowed_elements = {6, 7, 8, 16}
    multi_carbon_or_hydrogen_free_small = (
        len(carbon_atoms) >= 2
        and fragment.GetNumHeavyAtoms() <= 5
        and not has_carbon_hydrogen
        and all(
            atom.GetAtomicNum() in allowed_elements for atom in fragment.GetAtoms()
        )
    )
    return (
        carbon_only_anion
        or single_carbon_small
        or multi_carbon_or_hydrogen_free_small
    )


def leakage_connectivity_keys(fragments: tuple[Chem.Mol, ...]) -> list[str]:
    """生成原始多片段结构中所有潜在可建模有机组分的连接层键。"""
    keys: set[str] = set()
    for fragment in fragments:
        if not any(atom.GetAtomicNum() == 6 for atom in fragment.GetAtoms()):
            continue
        if known_inorganic_carbon_reason(fragment):
            continue
        if fragment.GetNumHeavyAtoms() < 2:
            continue
        try:
            candidate = rdMolStandardize.Uncharger().uncharge(fragment)
            tautomer_enumerator = rdMolStandardize.TautomerEnumerator()
            tautomer_enumerator.SetRemoveSp3Stereo(False)
            tautomer_enumerator.SetReassignStereo(True)
            candidate = tautomer_enumerator.Canonicalize(candidate)
            inchikey = Chem.MolToInchiKey(candidate)
        except (RuntimeError, ValueError):
            continue
        if inchikey:
            keys.add(inchikey.split("-", maxsplit=1)[0])
    return sorted(keys)


def empty_structure_result(smiles: str) -> dict[str, Any]:
    return {
        "raw_smiles": smiles,
        "canonical_smiles": "",
        "parent_smiles": "",
        "standard_inchikey": "",
        "connectivity_key": "",
        "murcko_scaffold": "",
        "rdkit_parse_ok": False,
        "rdkit_mol_ok": False,
        "leakage_connectivity_keys_json": "[]",
        "structure_category": EXCLUDED,
        "standardization_notes": "",
        "formal_charge_before": "",
        "formal_charge_after": "",
        "uncharging_applied": False,
        "residual_charge": False,
        "tautomer_standardized": False,
        "inorganic_carbon_review_required": False,
    }


def standardize_smiles(smiles: str) -> dict[str, Any]:
    result = empty_structure_result(smiles)
    notes = []
    if not smiles:
        result["standardization_notes"] = "缺少来源SMILES"
        return result
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        result["standardization_notes"] = "RDKit解析失败"
        return result
    result["rdkit_parse_ok"] = True
    if any(atom.GetAtomicNum() == 0 for atom in molecule.GetAtoms()):
        result["standardization_notes"] = "存在未定义原子或聚合物原子"
        return result
    try:
        cleaned = rdMolStandardize.Cleanup(molecule)
        result["canonical_smiles"] = Chem.MolToSmiles(
            cleaned, canonical=True, isomericSmiles=True
        )
        fragments = Chem.GetMolFrags(cleaned, asMols=True, sanitizeFrags=True)
        result["leakage_connectivity_keys_json"] = json_text(
            leakage_connectivity_keys(fragments)
        )
        inorganic_carbon = [
            (fragment, known_inorganic_carbon_reason(fragment))
            for fragment in fragments
        ]
        inorganic_carbon = [
            (fragment, reason) for fragment, reason in inorganic_carbon if reason
        ]
        inorganic_fragment_ids = {id(fragment) for fragment, _ in inorganic_carbon}
        remaining_fragments = [
            fragment for fragment in fragments if id(fragment) not in inorganic_fragment_ids
        ]
        organic = [
            fragment
            for fragment in remaining_fragments
            if any(atom.GetAtomicNum() == 6 for atom in fragment.GetAtoms())
        ]
        if not organic:
            reasons = sorted({reason for _, reason in inorganic_carbon})
            result["standardization_notes"] = (
                "仅含明确无机含碳片段：" + "、".join(reasons)
                if reasons
                else "无含碳有机片段"
            )
            return result
        if len(organic) > 1:
            result["standardization_notes"] = "多个有机片段混合物"
            return result
        parent = organic[0]
        extra_fragments = [
            fragment for fragment in fragments if id(fragment) != id(parent)
        ]
        neutral_extra_fragments = [
            fragment
            for fragment in extra_fragments
            if Chem.GetFormalCharge(fragment) == 0
        ]
        if neutral_extra_fragments:
            result["standardization_notes"] = (
                "存在中性共组分，按混合物、溶剂化物或加合物排除"
            )
            return result
        charge_before = Chem.GetFormalCharge(parent)
        if extra_fragments:
            extra_charges = [
                Chem.GetFormalCharge(fragment) for fragment in extra_fragments
            ]
            extra_total_charge = sum(extra_charges)
            balanced_counterions = (
                charge_before != 0
                and extra_total_charge != 0
                and charge_before * extra_total_charge < 0
                and charge_before + extra_total_charge == 0
                and all(charge_before * charge < 0 for charge in extra_charges)
            )
            if not balanced_counterions:
                result["standardization_notes"] = (
                    "多片段离子结构的电荷方向或化学计量不配平，无法确认对离子"
                )
                return result
        inorganic_review_required = requires_inorganic_carbon_review(parent)
        if inorganic_carbon:
            removed = "、".join(sorted({reason for _, reason in inorganic_carbon}))
            notes.append(f"已移除无机含碳对离子：{removed}")
        if extra_fragments:
            notes.append("已移除对离子")
        before_uncharging = Chem.MolToSmiles(
            parent, canonical=True, isomericSmiles=True
        )
        parent = rdMolStandardize.Uncharger().uncharge(parent)
        after_uncharging = Chem.MolToSmiles(
            parent, canonical=True, isomericSmiles=True
        )
        uncharging_applied = before_uncharging != after_uncharging
        if parent.GetNumHeavyAtoms() < 2:
            result["standardization_notes"] = "结构不明确或仅含一个重原子"
            return result
        before_tautomer = after_uncharging
        tautomer_enumerator = rdMolStandardize.TautomerEnumerator()
        # 保留四面体立体中心；RDKit 默认值 True 会丢失部分氨基酸等分子的手性。
        tautomer_enumerator.SetRemoveSp3Stereo(False)
        # 重新分配互变异构体规范化后仍然有效的立体信息。
        tautomer_enumerator.SetReassignStereo(True)
        parent = tautomer_enumerator.Canonicalize(parent)
        parent_smiles = Chem.MolToSmiles(parent, canonical=True, isomericSmiles=True)
        tautomer_standardized = before_tautomer != parent_smiles
        inchikey = Chem.MolToInchiKey(parent)
        if not inchikey:
            result["standardization_notes"] = "InChIKey生成失败"
            return result
        connectivity_key = inchikey.split("-", maxsplit=1)[0]
        charge_after = Chem.GetFormalCharge(parent)
        if charge_after:
            notes.append(f"保留形式电荷{charge_after:+d}")
        if tautomer_standardized:
            notes.append("已执行互变异构体规范化")
        if inorganic_review_required:
            notes.append("疑似无机含碳小分子，需人工审核")
        scaffold_mol = MurckoScaffold.GetScaffoldForMol(parent)
        scaffold = (
            Chem.MolToSmiles(
                scaffold_mol, canonical=True, isomericSmiles=False
            )
            if scaffold_mol
            else ""
        )
        result.update(
            {
                "parent_smiles": parent_smiles,
                "standard_inchikey": inchikey,
                "connectivity_key": connectivity_key,
                "murcko_scaffold": scaffold,
                "rdkit_mol_ok": True,
                "structure_category": (
                    "inorganic_carbon_review"
                    if inorganic_review_required
                    else "modelable"
                ),
                "standardization_notes": ";".join(notes),
                "formal_charge_before": charge_before,
                "formal_charge_after": charge_after,
                "uncharging_applied": uncharging_applied,
                "residual_charge": charge_after != 0,
                "tautomer_standardized": tautomer_standardized,
                "inorganic_carbon_review_required": inorganic_review_required,
            }
        )
    except (RuntimeError, ValueError) as error:
        result["standardization_notes"] = f"标准化失败：{type(error).__name__}"
    return result


def standardize_structure_tables(raw_dir: Path) -> pd.DataFrame:
    structure_columns = [
        "source",
        "source_chemical_id",
        "structure_source_record_id",
        "structure_source_status",
        "structure_source_error",
        "structure_provenance",
        "pubchem_sid",
        "pubchem_cid",
        "source_dtxsid",
        "source_connectivity_smiles",
        "source_pubchem_inchikey",
        *empty_structure_result("").keys(),
    ]
    frames = []
    for source in ("cpdb", "iris", "ccris"):
        frame = read_raw_csv(raw_dir / f"{source}_structures_raw.csv")
        require_columns(
            frame,
            {"source", "source_record_id", "source_smiles", "structure_status"},
            f"{source} 结构表",
        )
        rows = []
        for record in frame.to_dict(orient="records"):
            record_source = record["source"].strip().lower()
            raw_source_record_id = record["source_record_id"].strip()
            source_record_id = raw_source_record_id
            source_dtxsid = record.get("dtxsid", "").strip()
            structure_status = record["structure_status"].strip().lower()
            if record_source != source:
                raise ValueError(
                    f"{source} 结构表中的 source 值 {record['source']!r} 与文件来源不一致"
                )
            if not raw_source_record_id and source != "iris":
                raise ValueError(f"{source} 结构表存在空的 source_record_id")
            if source == "iris":
                source_dtxsid = normalize_dtxsid(source_dtxsid)
                source_record_id = iris_chemical_id(
                    source_dtxsid,
                    record.get("casrn", ""),
                    record.get("name", ""),
                )
                generic_raw_id = (
                    raw_source_record_id.casefold() in IDENTIFIER_PLACEHOLDERS
                )
                normalized_raw_id = raw_source_record_id
                if re.fullmatch(
                    r"DTXSID\d+", raw_source_record_id, flags=re.IGNORECASE
                ):
                    normalized_raw_id = raw_source_record_id.upper()
                if normalized_raw_id != source_record_id and not generic_raw_id:
                    raise ValueError(
                        f"IRIS 结构记录的原始关联键 {raw_source_record_id!r} "
                        f"与稳定关联键 {source_record_id!r} 不一致"
                    )
            if structure_status in ACCEPTED_STRUCTURE_STATUSES:
                standardized = standardize_smiles(record["source_smiles"])
            else:
                standardized = empty_structure_result(record["source_smiles"])
                source_error = record.get("structure_error", "").strip()
                standardized["standardization_notes"] = (
                    f"来源结构状态不可接受：{structure_status or '空值'}"
                    + (f"；{source_error}" if source_error else "")
                )
            rows.append(
                {
                    "source": source,
                    "source_chemical_id": source_record_id,
                    "structure_source_record_id": source_record_id,
                    "structure_source_status": structure_status,
                    "structure_source_error": record.get("structure_error", ""),
                    "structure_provenance": record.get("structure_provenance", ""),
                    "pubchem_sid": record.get("pubchem_sid", ""),
                    "pubchem_cid": record.get("pubchem_cid", ""),
                    "source_dtxsid": source_dtxsid,
                    "source_connectivity_smiles": record.get(
                        "connectivity_smiles", ""
                    ),
                    "source_pubchem_inchikey": record.get("pubchem_inchikey", ""),
                    **standardized,
                }
            )
        frames.append(pd.DataFrame(rows, columns=structure_columns))
    structures = pd.concat(frames, ignore_index=True)
    duplicate = structures.duplicated(["source", "source_chemical_id"], keep=False)
    if duplicate.any():
        values = structures.loc[duplicate, ["source", "source_chemical_id"]]
        raise ValueError(f"存在重复的结构关联键：\n{values.to_string(index=False)}")
    return structures


def apply_inorganic_carbon_decisions(
    structures: pd.DataFrame, decisions_path: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """校验并应用可复现的疑似无机含碳结构人工审核决策。"""
    columns = ["standard_inchikey", "decision", "review_reason", "reviewer"]
    required = set(columns)
    if decisions_path.exists():
        decisions = read_raw_csv(decisions_path)
        require_columns(decisions, required, "疑似无机含碳人工决策表")
        decisions = decisions[columns].copy()
    else:
        decisions = pd.DataFrame(columns=columns)

    for column in columns:
        decisions[column] = decisions[column].astype(str).str.strip()
    empty_key = decisions["standard_inchikey"].eq("")
    if empty_key.any():
        raise ValueError("疑似无机含碳人工决策表存在空 standard_inchikey")
    duplicate = decisions["standard_inchikey"].duplicated(keep=False)
    if duplicate.any():
        bad = decisions.loc[duplicate].sort_values("standard_inchikey")
        raise ValueError("疑似无机含碳人工决策存在重复键：\n" + bad.to_string(index=False))
    illegal = ~decisions["decision"].isin(["include", "exclude"])
    if illegal.any():
        bad = decisions.loc[illegal, ["standard_inchikey", "decision"]]
        raise ValueError("人工决策只能为 include 或 exclude：\n" + bad.to_string(index=False))
    incomplete = decisions["review_reason"].eq("") | decisions["reviewer"].eq("")
    if incomplete.any():
        bad = decisions.loc[
            incomplete,
            ["standard_inchikey", "review_reason", "reviewer"],
        ]
        raise ValueError("人工决策必须同时填写 review_reason 和 reviewer：\n" + bad.to_string(index=False))

    review_keys = set(
        structures.loc[
            structures["inorganic_carbon_review_required"].astype(bool),
            "standard_inchikey",
        ]
    )
    unknown = set(decisions["standard_inchikey"]) - review_keys
    if unknown:
        raise ValueError(
            "人工决策表包含未出现在当前疑似无机含碳审核集的 InChIKey："
            + "、".join(sorted(unknown))
        )

    result = structures.copy()
    result["manual_review_decision"] = ""
    result["manual_review_reason"] = ""
    result["manual_reviewer"] = ""
    for decision in decisions.to_dict(orient="records"):
        key = decision["standard_inchikey"]
        mask = result["standard_inchikey"].eq(key)
        result.loc[mask, "manual_review_decision"] = decision["decision"]
        result.loc[mask, "manual_review_reason"] = decision["review_reason"]
        result.loc[mask, "manual_reviewer"] = decision["reviewer"]
        category = "modelable" if decision["decision"] == "include" else "manual_excluded"
        result.loc[mask, "structure_category"] = category
        prefix = "人工审核纳入" if decision["decision"] == "include" else "人工审核排除"
        addition = f"{prefix}：{decision['review_reason']}；审核人：{decision['reviewer']}"
        result.loc[mask, "standardization_notes"] = result.loc[
            mask, "standardization_notes"
        ].map(lambda value: ";".join(part for part in [value, addition] if part))
    return result, decisions


def split_review_candidates(
    uncertain: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """按数据角色拆分弱证据候选，避免外部集候选被误用于训练。"""
    candidate_mask = uncertain["label_candidate"].isin([POSITIVE, NEGATIVE])
    development = uncertain.loc[
        candidate_mask & uncertain["dataset_role"].eq("development")
    ].copy()
    external = uncertain.loc[
        candidate_mask & uncertain["dataset_role"].eq("external")
    ].copy()
    return development, external


def collect_leakage_connectivity_keys(records: pd.DataFrame, role: str) -> set[str]:
    """汇总某数据角色中所有 RDKit 可解析结构的潜在有机组分连接键。"""
    values = records.loc[
        records["dataset_role"].eq(role)
        & records["rdkit_parse_ok"].fillna(False).astype(bool),
        "leakage_connectivity_keys_json",
    ]
    keys: set[str] = set()
    for value in values:
        try:
            parsed = json.loads(value or "[]")
        except json.JSONDecodeError as error:
            raise ValueError("泄漏连接键 JSON 解析失败") from error
        if not isinstance(parsed, list) or any(
            not isinstance(item, str) for item in parsed
        ):
            raise ValueError("泄漏连接键 JSON 必须是字符串列表")
        keys.update(item for item in parsed if item)
    return keys


def validate_ccris_excluded_only_keys(
    external_valid: pd.DataFrame, external_all: pd.DataFrame
) -> None:
    """确保只含 excluded CCRIS 证据的化合物未进入任何外部聚合集。"""
    excluded_only_keys = {
        inchikey
        for inchikey, group in external_valid.groupby("standard_inchikey")
        if set(group["label_category"]) == {EXCLUDED}
    }
    leaked_keys = excluded_only_keys & set(external_all["standard_inchikey"])
    if leaked_keys:
        raise AssertionError(
            "仅含 excluded 证据的 CCRIS 化合物被错误纳入外部聚合集："
            + "、".join(sorted(leaked_keys))
        )


def find_structure_representation_conflicts(records: pd.DataFrame) -> pd.DataFrame:
    """查找同一 standard InChIKey 对应多个 parent SMILES 的记录。"""
    valid = records[records["rdkit_mol_ok"].astype(bool)]
    rows = []
    for inchikey, group in valid.groupby("standard_inchikey", sort=True):
        parent_smiles = sorted(set(group["parent_smiles"]) - {""})
        if len(parent_smiles) <= 1:
            continue
        rows.append(
            {
                "standard_inchikey": inchikey,
                "connectivity_key": group.iloc[0]["connectivity_key"],
                "parent_smiles_json": json_text(parent_smiles),
                "source_json": json_text(sorted(set(group["source"]))),
                "source_record_id_json": json_text(
                    sorted(set(group["source_record_id"]))
                ),
                "record_count": len(group),
                "conflict_reason": "同一 standard InChIKey 对应多个 parent SMILES",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "standard_inchikey",
            "connectivity_key",
            "parent_smiles_json",
            "source_json",
            "source_record_id_json",
            "record_count",
            "conflict_reason",
        ],
    )


def aggregate_compounds(records: pd.DataFrame, role: str) -> pd.DataFrame:
    structure_ok_column = (
        "model_structure_ok" if "model_structure_ok" in records.columns else "rdkit_mol_ok"
    )
    valid = records[
        (records["dataset_role"] == role)
        & records[structure_ok_column].astype(bool)
        & (records["label_category"] != EXCLUDED)
    ]
    rows = []
    for inchikey, group in valid.groupby("standard_inchikey", sort=True):
        clear = set(group.loc[group["label_category"].isin([POSITIVE, NEGATIVE]), "label_category"])
        candidates = set(group.loc[group["label_candidate"].isin([POSITIVE, NEGATIVE]), "label_candidate"])
        if clear == {POSITIVE, NEGATIVE}:
            category, binary, confidence = CONFLICT, "", "none"
        elif clear == {POSITIVE}:
            category, binary, confidence = POSITIVE, 1, "high"
        elif clear == {NEGATIVE}:
            category, binary, confidence = NEGATIVE, 0, "high"
        else:
            category, binary = UNCERTAIN, ""
            confidence = "medium" if len(candidates) == 1 else "none"
        first = group.iloc[0]
        formal_charge_after_values = sorted(set(group["formal_charge_after"]))
        if len(formal_charge_after_values) != 1:
            raise ValueError(
                f"化合物 {inchikey} 聚合后存在不一致的 formal_charge_after："
                f"{formal_charge_after_values}"
            )
        standardization_notes = ";".join(
            sorted(set(group["standardization_notes"]) - {""})
        )
        evidence = group[
            [
                "source",
                "source_record_id",
                "label_raw",
                "label_category",
                "label_candidate",
                "label_confidence",
                "label_reason",
            ]
        ].to_dict(orient="records")
        candidate_label = next(iter(candidates)) if len(candidates) == 1 else ""
        rows.append(
            {
                "compound_id": f"{role.upper()}:{inchikey}",
                "dataset_role": role,
                "source": "|".join(sorted(set(group["source"]))),
                "source_record_id": json_text(sorted(set(group["source_record_id"]))),
                "casrn": "|".join(sorted(set(group["casrn"]) - {"", "$null"})),
                "name": first["name"],
                "raw_smiles": first["raw_smiles"],
                "canonical_smiles": first["canonical_smiles"],
                "parent_smiles": first["parent_smiles"],
                "standard_inchikey": inchikey,
                "connectivity_key": first["connectivity_key"],
                "murcko_scaffold": first["murcko_scaffold"],
                "label_raw": json_text(sorted(set(group["label_raw"]) - {""})),
                "label_binary": binary,
                "label_category": category,
                "label_candidate": candidate_label,
                "label_confidence": confidence,
                "endpoint": "carcinogenicity",
                "species": "|".join(sorted(set(group["species"]) - {""})),
                "route": "|".join(sorted(set(group["route"]) - {""})),
                "reference": json_text(sorted(set(group["reference"]) - {""})),
                "rdkit_mol_ok": True,
                "standardization_notes": standardization_notes,
                "formal_charge_before": json_text(
                    sorted(set(group["formal_charge_before"]))
                ),
                "formal_charge_after": formal_charge_after_values[0],
                "uncharging_applied": bool(group["uncharging_applied"].any()),
                "residual_charge": bool(group["residual_charge"].any()),
                "tautomer_standardized": bool(group["tautomer_standardized"].any()),
                "clear_positive_records": int((group["label_category"] == POSITIVE).sum()),
                "clear_negative_records": int((group["label_category"] == NEGATIVE).sum()),
                "uncertain_records": int((group["label_category"] == UNCERTAIN).sum()),
                "nonclear_disagreement": bool(
                    (category == POSITIVE and NEGATIVE in candidates)
                    or (category == NEGATIVE and POSITIVE in candidates)
                ),
                "external_overlap": False,
                "label_evidence_json": json_text(evidence),
            }
        )
    return pd.DataFrame(rows, columns=COMPOUND_COLUMNS)


def scaffold_connectivity_groups(development: pd.DataFrame) -> pd.Series:
    """按共享 Murcko 骨架或 connectivity_key 的连通分量生成划分组。"""
    parents = list(range(len(development)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    first_by_token: dict[str, int] = {}
    for position, row in enumerate(development.itertuples(index=False)):
        tokens = [f"CONNECTIVITY:{row.connectivity_key}"]
        if row.murcko_scaffold:
            tokens.append(f"SCAFFOLD:{row.murcko_scaffold}")
        for token in tokens:
            if token in first_by_token:
                union(position, first_by_token[token])
            else:
                first_by_token[token] = position
    return pd.Series(
        [f"GROUP:{find(position)}" for position in range(len(development))],
        index=development.index,
    )


def split_development(
    development: pd.DataFrame, config: CleaningConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if development.empty:
        raise ValueError("严格开发集为空，无法划分训练集和验证集")
    if development["label_binary"].nunique() < 2:
        raise ValueError("严格开发集没有同时包含阳性和阴性类别")
    if config.split_method == "none":
        return development.copy(), development.iloc[0:0].copy()
    if config.split_method == "random":
        train, validation = train_test_split(
            development,
            test_size=config.validation_size,
            random_state=config.random_seed,
            stratify=development["label_binary"],
        )
        return train.sort_values("standard_inchikey"), validation.sort_values(
            "standard_inchikey"
        )
    if config.split_method != "scaffold":
        raise ValueError(f"未知的数据划分方法：{config.split_method}")

    groups = scaffold_connectivity_groups(development)
    splitter = GroupShuffleSplit(
        n_splits=200,
        test_size=config.validation_size,
        random_state=config.random_seed,
    )
    overall_rate = development["label_binary"].astype(float).mean()
    best: tuple[float, Any, Any] | None = None
    for train_index, validation_index in splitter.split(
        development, development["label_binary"], groups
    ):
        train_candidate = development.iloc[train_index]
        validation_candidate = development.iloc[validation_index]
        if train_candidate["label_binary"].nunique() < 2:
            continue
        if validation_candidate["label_binary"].nunique() < 2:
            continue
        if set(train_candidate["connectivity_key"]) & set(
            validation_candidate["connectivity_key"]
        ):
            continue
        size_error = abs(
            len(validation_candidate) / len(development) - config.validation_size
        )
        train_rate_error = abs(
            train_candidate["label_binary"].astype(float).mean() - overall_rate
        )
        validation_rate_error = abs(
            validation_candidate["label_binary"].astype(float).mean() - overall_rate
        )
        score = size_error + train_rate_error + validation_rate_error
        if best is None or score < best[0]:
            best = (score, train_index, validation_index)
    if best is None:
        raise ValueError("未找到能同时保留两个二分类别的骨架划分方案")
    train = development.iloc[best[1]].sort_values("standard_inchikey")
    validation = development.iloc[best[2]].sort_values("standard_inchikey")
    return train, validation


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_signature() -> dict[str, str]:
    """返回可能影响标准化、划分和 CSV 输出的运行环境签名。"""
    signature = {
        "python": platform.python_version(),
        "rdkit": version("rdkit"),
        "numpy": version("numpy"),
        "pandas": version("pandas"),
        "scikit_learn": version("scikit-learn"),
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    signature.update(inchi_implementation_signature())
    return signature


def cleaning_code_paths(config: CleaningConfig) -> list[Path]:
    """列出清洗入口、项目模块和可用的环境锁定文件。"""
    paths = set((config.root / "src" / "carcinogenicity").rglob("*.py"))
    paths.add(Path(__file__).resolve())
    paths.add(config.root / "scripts" / "clean_datasets.py")
    for pattern in (
        "pyproject.toml",
        "requirements*.txt",
        "requirements*.lock",
        "uv.lock",
        "conda*.yml",
        "conda*.yaml",
        "environment*.yml",
        "environment*.yaml",
    ):
        paths.update(config.root.glob(pattern))
    return sorted(paths, key=lambda path: str(path.resolve()))


def cleaning_input_fingerprint(config: CleaningConfig) -> str:
    """对决定清洗结果的输入、代码和划分参数生成指纹。"""
    digest = hashlib.sha256()
    settings = {
        "split_method": config.split_method,
        "validation_size": config.validation_size,
        "random_seed": config.random_seed,
    }
    digest.update(json_text(settings).encode("utf-8"))
    digest.update(json_text(runtime_signature()).encode("utf-8"))
    input_paths = sorted(config.raw_dir.glob("*_raw.csv"))
    input_paths.append(config.inorganic_carbon_decisions_path)
    input_paths.extend(cleaning_code_paths(config))
    for path in input_paths:
        try:
            relative_name = str(path.resolve().relative_to(config.root.resolve()))
        except ValueError:
            relative_name = str(path.resolve())
        digest.update(relative_name.encode("utf-8"))
        digest.update(sha256(path).encode("ascii") if path.exists() else b"missing")
    return digest.hexdigest()


def create_run_id(input_fingerprint: str) -> str:
    """创建可排序且冲突概率极低的审计运行标识。"""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f_UTC")
    return f"{timestamp}_{input_fingerprint[:8]}"


def build_cleaning_manifest(
    config: CleaningConfig,
    *,
    run_id: str,
    input_fingerprint: str,
    output_files: dict[str, dict[str, Any]] | None = None,
    report_files: dict[str, dict[str, Any]] | None = None,
    support_files: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """生成可供正式运行校验的机器可读清洗清单。"""
    return {
        "manifest_version": 3,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_type": "audit" if config.dry_run else "formal",
        "input_fingerprint": input_fingerprint,
        "approved_audit_run": config.approved_audit_run,
        "runtime_signature": runtime_signature(),
        "output_files": output_files or {},
        "report_files": report_files or {},
        "support_files": support_files or {},
        "settings": {
            "split_method": config.split_method,
            "validation_size": config.validation_size,
            "random_seed": config.random_seed,
        },
    }


def validate_approved_audit(
    config: CleaningConfig, input_fingerprint: str
) -> dict[str, Any]:
    """确认正式运行引用的审计批次存在且输入未变更。"""
    run_id = config.approved_audit_run.strip()
    if not run_id:
        raise ValueError("正式运行必须通过 --approved-audit-run 指定已审核批次")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
        raise ValueError("--approved-audit-run 包含非法字符")
    manifest_path = (
        config.cleaning_reports_dir / "audits" / run_id / "cleaning_manifest.json"
    )
    if not manifest_path.is_file():
        raise ValueError(f"找不到已审核批次清单：{manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取已审核批次清单：{manifest_path}") from error
    if manifest.get("manifest_version") != 3:
        raise ValueError("已审核批次清单版本过旧，请重新执行 --dry-run")
    if manifest.get("run_type") != "audit":
        raise ValueError("指定的批次不是 --dry-run 审计运行")
    if manifest.get("run_id") != run_id:
        raise ValueError("已审核批次目录名与清单中的 run_id 不一致")
    if manifest.get("runtime_signature") != runtime_signature():
        raise ValueError("当前运行环境与已审核批次不一致")
    if manifest.get("input_fingerprint") != input_fingerprint:
        raise ValueError(
            "当前原始数据、人工决策、清洗代码或划分参数已变更；"
            "请重新执行 --dry-run 并审核新批次"
        )
    return manifest


def output_file_manifest(
    outputs: dict[str, pd.DataFrame], output_dir: Path
) -> dict[str, dict[str, Any]]:
    """记录所有拟发布 CSV 的逐字节哈希和数据行数。"""
    return {
        filename: {
            "sha256": sha256(output_dir / filename),
            "rows": len(frame),
        }
        for filename, frame in sorted(outputs.items())
    }


def validate_output_file_manifest(
    approved_manifest: dict[str, Any], current_outputs: dict[str, dict[str, Any]]
) -> None:
    """确保正式输出与已审核的拟输出逐文件一致。"""
    approved_outputs = approved_manifest.get("output_files")
    if not isinstance(approved_outputs, dict) or not approved_outputs:
        raise ValueError("已审核批次未记录正式输出哈希，请重新执行 --dry-run")
    validate_artifact_manifest(approved_outputs, current_outputs, "正式输出")


def validate_artifact_manifest(
    expected: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
    artifact_name: str,
) -> None:
    """比较一组审计工件的文件集合、哈希和行数。"""
    if expected == current:
        return
    expected_names = set(expected)
    current_names = set(current)
    missing = sorted(expected_names - current_names)
    added = sorted(current_names - expected_names)
    changed = sorted(
        name
        for name in expected_names & current_names
        if expected[name] != current[name]
    )
    details = []
    if missing:
        details.append("缺少文件：" + "、".join(missing))
    if added:
        details.append("新增文件：" + "、".join(added))
    if changed:
        details.append("哈希或行数变化：" + "、".join(changed))
    raise ValueError(f"{artifact_name}与已审核记录不一致；" + "；".join(details))


def csv_directory_manifest(directory: Path) -> dict[str, dict[str, Any]]:
    """重新计算目录中所有 CSV 的哈希和数据行数。"""
    if not directory.is_dir():
        raise ValueError(f"审计 CSV 目录不存在：{directory}")
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.csv")):
        try:
            rows = len(pd.read_csv(path, dtype=str, keep_default_na=False))
        except (
            OSError,
            UnicodeError,
            pd.errors.ParserError,
            pd.errors.EmptyDataError,
        ) as error:
            raise ValueError(f"审计 CSV 无法读取：{path}") from error
        result[path.name] = {"sha256": sha256(path), "rows": rows}
    return result


def validate_audit_artifacts(
    config: CleaningConfig, approved_manifest: dict[str, Any]
) -> None:
    """确认人工审核目录中的数据、报告和日志未被修改。"""
    audit_dir = (
        config.cleaning_reports_dir / "audits" / config.approved_audit_run.strip()
    )
    approved_outputs = approved_manifest.get("output_files")
    approved_reports = approved_manifest.get("report_files")
    approved_support = approved_manifest.get("support_files")
    if not isinstance(approved_outputs, dict) or not approved_outputs:
        raise ValueError("已审核批次未记录数据工件")
    if not isinstance(approved_reports, dict) or not approved_reports:
        raise ValueError("已审核批次未记录报告工件")
    if not isinstance(approved_support, dict) or not approved_support:
        raise ValueError("已审核批次未记录辅助工件")
    validate_artifact_manifest(
        approved_outputs,
        csv_directory_manifest(audit_dir / "datasets"),
        "审计数据工件",
    )
    validate_artifact_manifest(
        approved_reports,
        csv_directory_manifest(audit_dir),
        "审计报告工件",
    )
    current_support: dict[str, dict[str, Any]] = {}
    for filename in approved_support:
        path = audit_dir / filename
        if path.is_file():
            current_support[filename] = {"sha256": sha256(path)}
    validate_artifact_manifest(
        approved_support, current_support, "审计辅助工件"
    )


def split_report(train: pd.DataFrame, validation: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, frame in (("train", train), ("validation", validation)):
        for label, count in frame["label_binary"].value_counts().sort_index().items():
            rows.append(
                {"split": name, "dimension": "label_binary", "value": label, "count": count}
            )
        for source, count in frame["source"].value_counts().sort_index().items():
            rows.append(
                {"split": name, "dimension": "source", "value": source, "count": count}
            )
    return pd.DataFrame(rows)


def connectivity_overlap_report(
    train: pd.DataFrame, validation: pd.DataFrame
) -> pd.DataFrame:
    """生成训练集与验证集之间的连接层重叠报告。"""
    shared = sorted(
        (set(train["connectivity_key"]) - {""})
        & (set(validation["connectivity_key"]) - {""})
    )
    rows = []
    for key in shared:
        train_rows = train[train["connectivity_key"] == key]
        validation_rows = validation[validation["connectivity_key"] == key]
        rows.append(
            {
                "connectivity_key": key,
                "train_inchikey_json": json_text(
                    sorted(set(train_rows["standard_inchikey"]))
                ),
                "validation_inchikey_json": json_text(
                    sorted(set(validation_rows["standard_inchikey"]))
                ),
                "train_compound_id_json": json_text(
                    sorted(set(train_rows["compound_id"]))
                ),
                "validation_compound_id_json": json_text(
                    sorted(set(validation_rows["compound_id"]))
                ),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "connectivity_key",
            "train_inchikey_json",
            "validation_inchikey_json",
            "train_compound_id_json",
            "validation_compound_id_json",
        ],
    )


def inchi_implementation_signature() -> dict[str, str]:
    """记录 InChI 库版本；旧版 RDKit 无版本 API 时使用二进制指纹锁定实现。"""
    binary_paths = inchi_binary_paths()
    digest = hashlib.sha256()
    for path in sorted(binary_paths, key=lambda item: str(item)):
        if not path.is_file():
            continue
        digest.update(path.name.encode("utf-8"))
        digest.update(sha256(path).encode("ascii"))
    return {
        "inchi_library_version": inchi_library_version(),
        "inchi_implementation_sha256": digest.hexdigest(),
    }


def inchi_binary_paths() -> set[Path]:
    """列出 RDKit InChI 扩展及 wheel 或本地安装中的链接 InChI 库。"""
    binary_paths = {Path(rdinchi.__file__).resolve()}
    rdkit_root = Path(Chem.__file__).resolve().parent.parent
    distribution_root = rdkit_root.parent
    for directory in (
        rdkit_root / ".dylibs",
        rdkit_root / ".libs",
        distribution_root / "rdkit.libs",
    ):
        if directory.is_dir():
            binary_paths.update(directory.glob("*Inchi*"))
            binary_paths.update(directory.glob("*inchi*"))
    return {path.resolve() for path in binary_paths if path.is_file()}


def inchi_library_version() -> str:
    """返回 InChI 库版本，并兼容没有 GetInchiVersion API 的旧版 RDKit。"""
    version_getter = getattr(Chem, "GetInchiVersion", None)
    if callable(version_getter):
        value = str(version_getter()).strip()
        if value:
            return value
    probe = Chem.MolFromSmiles("C")
    if probe is None:
        raise RuntimeError("无法创建 InChI 版本探针分子")
    result = rdinchi.MolToInchi(probe, "-?")
    log = result[3] if len(result) > 3 else ""
    first_line = next(
        (line.strip() for line in log.splitlines() if "InChI version" in line),
        "",
    )
    if not first_line:
        raise RuntimeError("无法从 RDKit InChI 日志解析库版本")
    return first_line


def replace_directories_transaction(replacements: list[tuple[Path, Path]]) -> None:
    """在同一交易中替换多个目录，任一替换失败时全部回滚。"""
    backups: list[tuple[Path, Path]] = []
    committed: list[Path] = []
    try:
        for _, destination in replacements:
            destination.parent.mkdir(parents=True, exist_ok=True)
            backup = destination.with_name(destination.name + ".cleaning_backup")
            if backup.exists():
                shutil.rmtree(backup)
            if destination.exists():
                destination.replace(backup)
                backups.append((backup, destination))
        for staged, destination in replacements:
            staged.replace(destination)
            committed.append(destination)
    except Exception:
        for destination in reversed(committed):
            if destination.exists():
                shutil.rmtree(destination)
        for backup, destination in reversed(backups):
            if backup.exists():
                backup.replace(destination)
        raise
    for backup, _ in backups:
        if backup.exists():
            shutil.rmtree(backup)


def cleaning_log(
    config: CleaningConfig,
    run_id: str,
    input_fingerprint: str,
    records: pd.DataFrame,
    development: pd.DataFrame,
    external: pd.DataFrame,
    conflicts: pd.DataFrame,
    uncertain: pd.DataFrame,
    excluded: pd.DataFrame,
    overlaps: pd.DataFrame,
    discordant: pd.DataFrame,
    representation_conflicts: pd.DataFrame,
    split_connectivity_overlaps: pd.DataFrame,
    inorganic_carbon_review: pd.DataFrame,
    manual_decisions: pd.DataFrame,
    development_review_candidates: pd.DataFrame,
    external_review_candidates: pd.DataFrame,
) -> str:
    raw_files = sorted(config.raw_dir.glob("*_raw.csv"))
    checksums = "\n".join(f"- `{path.name}`: `{sha256(path)}`" for path in raw_files)
    if config.inorganic_carbon_decisions_path.exists():
        checksums += (
            "\n- `data/manual/inorganic_carbon_decisions.csv`: `"
            + sha256(config.inorganic_carbon_decisions_path)
            + "`"
        )
    exclusion_counts = (
        excluded["exclusion_reason"]
        .fillna("未指定")
        .replace("", "未指定")
        .value_counts()
    )
    exclusion_summary = "\n".join(
        f"- {reason}: {count:,}" for reason, count in exclusion_counts.items()
    )
    return f"""# 数据清洗日志

## 运行环境

- Python: {platform.python_version()}
- RDKit: {version('rdkit')}
- pandas: {version('pandas')}
- scikit-learn: {version('scikit-learn')}
- InChI 库版本: {runtime_signature()['inchi_library_version']}
- InChI 实现 SHA-256: {runtime_signature()['inchi_implementation_sha256']}
- 数据划分方法: {config.split_method}
- 验证集比例: {config.validation_size}
- 随机种子: {config.random_seed}
- 审计运行: {config.dry_run}
- 运行 ID: {run_id}
- 输入指纹: {input_fingerprint}
- 已批准审计批次: {config.approved_audit_run or '不适用'}

## 数据量统计

- 规范化后的来源记录: {len(records):,}
- 严格开发集化合物: {len(development):,}
- 不重叠的外部 CCRIS 化合物: {len(external):,}
- 标签冲突化合物: {len(conflicts):,}
- 标签不确定化合物: {len(uncertain):,}
- 被排除的来源记录: {len(excluded):,}
- 外部集重叠化合物: {len(overlaps):,}
- 明确标签与相反弱证据并存的化合物: {len(discordant):,}
- 结构表示冲突: {len(representation_conflicts):,}
- 训练集/验证集连接层重叠: {len(split_connectivity_overlaps):,}
- 疑似无机含碳待审核结构: {len(inorganic_carbon_review):,}
- 已录入的疑似无机含碳人工决策: {len(manual_decisions):,}
- 开发集弱证据候选: {len(development_review_candidates):,}
- 外部集弱证据候选: {len(external_review_candidates):,}

## 排除原因

{exclusion_summary or '- 无'}

## 原始文件 SHA-256

{checksums}

## 策略摘要

只有明确的阳性或阴性证据可进入严格二分类数据集。较弱证据、证据不明确、证据不足、标签冲突、
结构无法解析、混合物、聚合物和无机物记录都保留在审计或审查输出中。如果外部 CCRIS 化合物的
连接层键 connectivity_key 出现在任何 CPDB 或 IRIS 记录中，则从外部测试集中移除。
"""


def run_cleaning(config: CleaningConfig) -> None:
    input_fingerprint = cleaning_input_fingerprint(config)
    approved_manifest: dict[str, Any] | None = None
    if not config.dry_run:
        approved_manifest = validate_approved_audit(config, input_fingerprint)
        validate_audit_artifacts(config, approved_manifest)
    run_id = create_run_id(input_fingerprint)
    structures = standardize_structure_tables(config.raw_dir)
    source_records = pd.concat(
        [
            normalize_cpdb(config.raw_dir),
            normalize_iris(config.raw_dir),
            normalize_ccris(config.raw_dir),
        ],
        ignore_index=True,
    )
    if source_records.empty:
        raise ValueError("所有来源数据均为空，无法构建开发集")
    structures, manual_decisions = apply_inorganic_carbon_decisions(
        structures, config.inorganic_carbon_decisions_path
    )
    validate_source_record_ids(source_records)
    records = source_records.merge(
        structures,
        on=["source", "source_chemical_id"],
        how="left",
        validate="many_to_one",
    )
    missing_structure_link = records["structure_source_record_id"].isna() | (
        records["structure_source_record_id"].astype(str).str.strip() == ""
    )
    if missing_structure_link.any():
        missing = records.loc[
            missing_structure_link, ["source", "source_chemical_id"]
        ].drop_duplicates()
        raise ValueError(
            "存在未关联到结构表的来源化学物：\n"
            + missing.to_string(index=False)
        )
    iris_records = records[records["source"] == "iris"]
    iris_dtxsid = iris_records["source_dtxsid"].fillna("").astype(str).str.strip()
    iris_mismatch = (iris_dtxsid != "") & (
        iris_dtxsid != iris_records["source_chemical_id"].astype(str).str.strip()
    )
    if iris_mismatch.any():
        mismatches = iris_records.loc[
            iris_mismatch, ["source_chemical_id", "source_dtxsid"]
        ].drop_duplicates()
        raise ValueError(
            "IRIS 原始记录与结构表的 DTXSID 不一致：\n"
            + mismatches.to_string(index=False)
        )
    records["rdkit_parse_ok"] = records["rdkit_parse_ok"].fillna(False).astype(bool)
    records["rdkit_mol_ok"] = records["rdkit_mol_ok"].fillna(False).astype(bool)
    representation_conflicts = find_structure_representation_conflicts(records)
    representation_conflict_keys = set(
        representation_conflicts["standard_inchikey"]
    )
    records["model_structure_ok"] = (
        records["rdkit_mol_ok"]
        & (records["structure_category"] == "modelable")
        & ~records["standard_inchikey"].isin(representation_conflict_keys)
    )
    records["exclusion_reason"] = ""
    records.loc[~records["rdkit_mol_ok"], "exclusion_reason"] = records.loc[
        ~records["rdkit_mol_ok"], "standardization_notes"
    ].fillna("缺少结构记录")
    representation_mask = records["standard_inchikey"].isin(
        representation_conflict_keys
    )
    records.loc[representation_mask, "exclusion_reason"] = (
        "同一 standard InChIKey 对应多个 parent SMILES"
    )
    nonmodel_category_mask = records["rdkit_mol_ok"] & records[
        "structure_category"
    ].ne("modelable")
    records.loc[nonmodel_category_mask, "exclusion_reason"] = records.loc[
        nonmodel_category_mask, "standardization_notes"
    ]
    label_excluded_mask = (records["label_category"] == EXCLUDED) & (
        records["exclusion_reason"] == ""
    )
    records.loc[label_excluded_mask, "exclusion_reason"] = records.loc[
        label_excluded_mask, "label_reason"
    ]

    development_all = aggregate_compounds(records, "development")
    external_all = aggregate_compounds(records, "external")
    development_full_keys = set(
        records.loc[
            (records["dataset_role"] == "development")
            & records["rdkit_mol_ok"],
            "standard_inchikey",
        ]
    )
    development_connectivity_keys = collect_leakage_connectivity_keys(
        records, "development"
    )
    overlap_mask = external_all["connectivity_key"].isin(
        development_connectivity_keys
    )
    external_all["external_overlap"] = overlap_mask
    overlaps = external_all.loc[overlap_mask].copy()
    overlaps["full_inchikey_overlap"] = overlaps["standard_inchikey"].isin(
        development_full_keys
    )
    overlaps["connectivity_overlap"] = True
    overlaps["overlap_reason"] = overlaps["full_inchikey_overlap"].map(
        {
            True: "完整InChIKey与连接层键均存在于CPDB或IRIS中",
            False: "连接层键存在于CPDB或IRIS中",
        }
    )
    external_nonoverlap = external_all.loc[~overlap_mask].copy()

    development = development_all[
        development_all["label_category"].isin([POSITIVE, NEGATIVE])
    ].copy()
    external = external_nonoverlap[
        external_nonoverlap["label_category"].isin([POSITIVE, NEGATIVE])
    ].copy()
    conflicts = pd.concat(
        [
            development_all[development_all["label_category"] == CONFLICT],
            external_all[external_all["label_category"] == CONFLICT],
        ],
        ignore_index=True,
    )
    uncertain = pd.concat(
        [
            development_all[development_all["label_category"] == UNCERTAIN],
            external_all[external_all["label_category"] == UNCERTAIN],
        ],
        ignore_index=True,
    )
    development_review_candidates, external_review_candidates = (
        split_review_candidates(uncertain)
    )
    discordant = pd.concat(
        [
            development[development["nonclear_disagreement"]],
            external_all[
                external_all["label_category"].isin([POSITIVE, NEGATIVE])
                & external_all["nonclear_disagreement"]
            ],
        ],
        ignore_index=True,
    )
    excluded = records[
        (~records["model_structure_ok"]) | (records["label_category"] == EXCLUDED)
    ].copy()
    inorganic_carbon_review = (
        records.loc[
            records["inorganic_carbon_review_required"].astype(bool),
            [
                "source",
                "source_chemical_id",
                "casrn",
                "name",
                "raw_smiles",
                "canonical_smiles",
                "parent_smiles",
                "standard_inchikey",
                "connectivity_key",
                "structure_category",
                "standardization_notes",
                "manual_review_decision",
                "manual_review_reason",
                "manual_reviewer",
                "structure_provenance",
            ],
        ]
        .drop_duplicates(["source", "source_chemical_id"])
        .sort_values(["source", "source_chemical_id"])
    )

    external_valid = records[
        (records["dataset_role"] == "external") & records["model_structure_ok"]
    ]
    validate_ccris_excluded_only_keys(external_valid, external_all)

    train, validation = split_development(development, config)
    if not development["standard_inchikey"].is_unique:
        raise AssertionError("development_pool 的 standard_inchikey 不唯一")
    if not external["standard_inchikey"].is_unique:
        raise AssertionError("external_ccris_test 的 standard_inchikey 不唯一")
    if set(development["connectivity_key"]) & set(external["connectivity_key"]):
        raise AssertionError("开发集与外部测试集之间存在连接层泄漏")
    split_union = set(train["standard_inchikey"]) | set(
        validation["standard_inchikey"]
    )
    if split_union != set(development["standard_inchikey"]):
        raise AssertionError("训练集与验证集未完整覆盖 development_pool")
    if set(train["standard_inchikey"]) & set(validation["standard_inchikey"]):
        raise AssertionError("训练集与验证集之间存在 InChIKey 泄漏")
    if not development["label_binary"].isin([0, 1]).all():
        raise AssertionError("development_pool 存在非 0/1 的 label_binary")
    if not external["label_binary"].isin([0, 1]).all():
        raise AssertionError("external_ccris_test 存在非 0/1 的 label_binary")
    if config.split_method == "scaffold":
        train_scaffolds = set(train["murcko_scaffold"]) - {""}
        validation_scaffolds = set(validation["murcko_scaffold"]) - {""}
        if train_scaffolds & validation_scaffolds:
            raise AssertionError("训练集与验证集之间存在 Murcko 骨架泄漏")
        if set(train["connectivity_key"]) & set(validation["connectivity_key"]):
            raise AssertionError(
                "scaffold 划分的训练集与验证集之间存在连接层泄漏"
            )

    split_connectivity_overlaps = connectivity_overlap_report(train, validation)

    outputs = {
        "source_records_audit.csv": records,
        "development_pool.csv": development,
        "train.csv": train,
        "validation.csv": validation,
        "external_ccris_test.csv": external,
        "conflict_set.csv": conflicts,
        "uncertain_set.csv": uncertain,
        "development_review_candidates.csv": development_review_candidates,
        "external_review_candidates.csv": external_review_candidates,
        "discordant_evidence_set.csv": discordant,
        "structure_representation_conflict.csv": representation_conflicts,
        "inorganic_carbon_review.csv": inorganic_carbon_review,
        "excluded_set.csv": excluded,
    }
    label_report = (
        records.groupby(
            ["source", "label_category", "label_candidate", "label_reason"],
            dropna=False,
        )
        .size()
        .rename("count")
        .reset_index()
    )
    raw_label_report = (
        records.groupby(
            [
                "source",
                "label_raw",
                "label_category",
                "label_candidate",
                "label_reason",
            ],
            dropna=False,
        )
        .size()
        .rename("count")
        .reset_index()
    )
    log = cleaning_log(
        config,
        run_id,
        input_fingerprint,
        records,
        development,
        external,
        conflicts,
        uncertain,
        excluded,
        overlaps,
        discordant,
        representation_conflicts,
        split_connectivity_overlaps,
        inorganic_carbon_review,
        manual_decisions,
        development_review_candidates,
        external_review_candidates,
    )

    stage_root = Path(tempfile.mkdtemp(prefix=".cleaning_staging_", dir=config.root))
    stage_processed = stage_root / "processed"
    stage_reports = stage_root / "reports"
    try:
        for filename, frame in outputs.items():
            write_csv(frame, stage_processed / filename)
        output_files = output_file_manifest(outputs, stage_processed)
        if approved_manifest is not None:
            validate_output_file_manifest(approved_manifest, output_files)

        reports = {
            "overlap_report.csv": overlaps,
            "split_report.csv": split_report(train, validation),
            "connectivity_overlap_report.csv": split_connectivity_overlaps,
            "label_mapping_report.csv": label_report,
            "raw_label_mapping_report.csv": raw_label_report,
            "discordant_evidence_report.csv": discordant,
            "structure_representation_conflict_report.csv": representation_conflicts,
            "inorganic_carbon_review.csv": inorganic_carbon_review,
            "development_review_candidates.csv": development_review_candidates,
            "external_review_candidates.csv": external_review_candidates,
        }
        for filename, frame in reports.items():
            write_csv(frame, stage_reports / filename)
        (stage_reports / "cleaning_log.md").write_text(log, encoding="utf-8")
        report_files = output_file_manifest(reports, stage_reports)
        support_files = {
            "cleaning_log.md": {
                "sha256": sha256(stage_reports / "cleaning_log.md")
            }
        }
        if approved_manifest is not None:
            approved_reports = approved_manifest.get("report_files")
            if not isinstance(approved_reports, dict) or not approved_reports:
                raise ValueError("已审核批次未记录报告工件")
            validate_artifact_manifest(
                approved_reports, report_files, "正式审核报告"
            )
        manifest = build_cleaning_manifest(
            config,
            run_id=run_id,
            input_fingerprint=input_fingerprint,
            output_files=output_files,
            report_files=report_files,
            support_files=support_files,
        )
        (stage_reports / "cleaning_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        if config.dry_run:
            stage_processed.replace(stage_reports / "datasets")
            audit_destination = config.cleaning_reports_dir / "audits" / run_id
            audit_destination.parent.mkdir(parents=True, exist_ok=True)
            if audit_destination.exists():
                raise FileExistsError(f"审计批次目录已存在：{audit_destination}")
            stage_reports.replace(audit_destination)
        else:
            replace_directories_transaction(
                [
                    (stage_processed, config.processed_dir),
                    (stage_reports, config.cleaning_reports_dir / "current"),
                ]
            )
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)
