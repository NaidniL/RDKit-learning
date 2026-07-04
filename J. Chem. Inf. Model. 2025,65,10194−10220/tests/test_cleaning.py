"""数据清洗关键化学规则的回归测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from rdkit import Chem
from rdkit.Chem import rdinchi


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcinogenicity.cleaning import (  # noqa: E402
    COMPOUND_COLUMNS,
    CleaningConfig,
    aggregate_compounds,
    apply_inorganic_carbon_decisions,
    build_cleaning_manifest,
    cleaning_input_fingerprint,
    collect_leakage_connectivity_keys,
    csv_directory_manifest,
    inchi_binary_paths,
    inchi_library_version,
    iris_chemical_id,
    normalize_dtxsid,
    output_file_manifest,
    runtime_signature,
    run_cleaning,
    scaffold_connectivity_groups,
    sha256,
    split_development,
    split_review_candidates,
    standardize_smiles,
    standardize_structure_tables,
    validate_approved_audit,
    validate_audit_artifacts,
    validate_ccris_excluded_only_keys,
    validate_output_file_manifest,
    validate_source_record_ids,
    write_csv,
)


def test_tautomer_standardization_preserves_sp3_stereo() -> None:
    """互变异构体规范化不应合并丙氨酸对映体。"""
    left = standardize_smiles("N[C@@H](C)C(=O)O")
    right = standardize_smiles("N[C@H](C)C(=O)O")

    assert left["rdkit_mol_ok"]
    assert right["rdkit_mol_ok"]
    assert left["standard_inchikey"] != right["standard_inchikey"]
    assert left["connectivity_key"] == right["connectivity_key"]


def test_empty_aggregation_retains_compound_schema() -> None:
    """无可聚合记录时仍应返回带固定表头的空表。"""
    records = pd.DataFrame(
        columns=[
            "dataset_role",
            "rdkit_mol_ok",
            "label_category",
            "label_candidate",
            "standard_inchikey",
        ]
    )

    result = aggregate_compounds(records, "external")

    assert result.empty
    assert list(result.columns) == COMPOUND_COLUMNS


def test_iris_placeholder_casrn_uses_unique_stable_name_key() -> None:
    """IRIS 缺少 DTXSID 且 CASRN 为 Various 时，名称应生成稳定且唯一的关联键。"""
    mercury = iris_chemical_id("", "Various", "Mercury Salts, Inorganic")
    vanadium = iris_chemical_id("", "Various", "Vanadium and Compounds")

    assert mercury.startswith("IRIS-NAME:")
    assert mercury == iris_chemical_id("", "various", " mercury  salts, inorganic ")
    assert mercury != vanadium
    assert iris_chemical_id("DTXSID123", "Various", "Name") == "DTXSID123"
    assert iris_chemical_id("N/A", "50-00-0", "Name") == "50-00-0"
    assert normalize_dtxsid(" dtxsid123 ") == "DTXSID123"
    with pytest.raises(ValueError, match="缺少 DTXSID"):
        iris_chemical_id("N/A", "Various", "Unknown")


@pytest.mark.parametrize(
    ("dtxsid", "casrn", "message"),
    [
        ("BAD-DTXSID", "50-00-0", "DTXSID 格式非法"),
        ("", "50-00-X", "CASRN 格式非法"),
        ("", "50-00-1", "CASRN 校验位错误"),
    ],
)
def test_iris_invalid_nonplaceholder_identifier_is_rejected(
    dtxsid: str, casrn: str, message: str
) -> None:
    """IRIS 非占位但格式或校验位非法的标识符必须报错。"""
    with pytest.raises(ValueError, match=message):
        iris_chemical_id(dtxsid, casrn, "Name")


def test_real_iris_label_and_structure_keys_match() -> None:
    """真实 IRIS 标签表与结构表应生成完全一致且唯一的关联键。"""
    raw_dir = ROOT / "data" / "raw"
    labels = pd.read_csv(
        raw_dir / "iris_raw.csv", dtype=str, keep_default_na=False
    )
    structures = pd.read_csv(
        raw_dir / "iris_structures_raw.csv", dtype=str, keep_default_na=False
    )
    label_keys = [
        iris_chemical_id(row.DTXSID, row.CASRN, row.chemical_name)
        for row in labels.rename(columns={"CHEMICAL NAME": "chemical_name"}).itertuples(
            index=False
        )
    ]
    structure_keys = [
        iris_chemical_id(row.dtxsid, row.casrn, row.name)
        for row in structures.itertuples(index=False)
    ]

    assert len(label_keys) == len(set(label_keys)) == 577
    assert len(structure_keys) == len(set(structure_keys)) == 577
    assert set(label_keys) == set(structure_keys)


def test_iris_structure_dtxsid_comparison_is_case_insensitive(tmp_path: Path) -> None:
    """结构表中大小写不同但语义相同的 DTXSID 应规范后通过。"""
    for source in ("cpdb", "ccris"):
        pd.DataFrame(
            columns=[
                "source",
                "source_record_id",
                "source_smiles",
                "structure_status",
            ]
        ).to_csv(tmp_path / f"{source}_structures_raw.csv", index=False)
    iris_path = tmp_path / "iris_structures_raw.csv"
    pd.DataFrame(
        [
            {
                "source": "iris",
                "source_record_id": "dtxsid123",
                "dtxsid": "dtxsid123",
                "casrn": "Various",
                "name": "Test chemical",
                "source_smiles": "CC",
                "structure_status": "ok",
            }
        ]
    ).to_csv(iris_path, index=False)

    structures = standardize_structure_tables(tmp_path)

    assert structures.loc[0, "source_chemical_id"] == "DTXSID123"
    assert structures.loc[0, "source_dtxsid"] == "DTXSID123"
    frame = pd.read_csv(iris_path, dtype=str, keep_default_na=False)
    frame.loc[0, "source_record_id"] = "DTXSID999"
    frame.to_csv(iris_path, index=False)
    with pytest.raises(ValueError, match="与稳定关联键"):
        standardize_structure_tables(tmp_path)


@pytest.mark.parametrize(
    "smiles",
    [
        "O=C=O",
        "[O-]C(=O)[O-].[Ca+2]",
        "[C-]#N.[Na+]",
        "S=C=S",
    ],
)
def test_known_inorganic_carbon_is_excluded(smiles: str) -> None:
    """明确无机含碳结构不应进入模型数据。"""
    result = standardize_smiles(smiles)

    assert not result["rdkit_mol_ok"]
    assert result["structure_category"] == "excluded"


def test_calcium_carbide_does_not_become_acetylene() -> None:
    """碳化钙中的二碳阴离子不得在去盐后被当作乙炔。"""
    result = standardize_smiles("[Ca+2].[C-]#[C-]")

    assert not result["rdkit_mol_ok"]
    assert result["structure_category"] == "excluded"
    assert "碳化物或金属乙炔化物" in result["standardization_notes"]


def test_hydrogenated_acetylide_requires_review() -> None:
    """含氢乙炔基负离子不得自动归类为无氢碳化物。"""
    result = standardize_smiles("[Na+].[C-]#C")

    assert result["rdkit_mol_ok"]
    assert result["structure_category"] == "inorganic_carbon_review"
    assert "碳化物或金属乙炔化物" not in result[
        "standardization_notes"
    ]


@pytest.mark.parametrize("smiles", ["O=C=C=C=O", "N#CC#N"])
def test_hydrogen_free_multi_carbon_structure_requires_review(smiles: str) -> None:
    """小型无氢多碳边界结构应进入人工审核。"""
    result = standardize_smiles(smiles)

    assert result["rdkit_mol_ok"]
    assert result["structure_category"] == "inorganic_carbon_review"
    assert result["inorganic_carbon_review_required"]


def test_small_single_carbon_structure_requires_review() -> None:
    """未列入明确无机表的小型单碳结构应进入人工审核。"""
    result = standardize_smiles("C=O")

    assert result["rdkit_mol_ok"]
    assert result["structure_category"] == "inorganic_carbon_review"


def test_inorganic_carbon_counterion_is_removed() -> None:
    """碳酸氢根作为对离子时应移除，不应被误判为多有机片段混合物。"""
    result = standardize_smiles("C[N+](C)(C)C.O=C([O-])O")

    assert result["rdkit_mol_ok"]
    assert result["structure_category"] == "modelable"
    assert "已移除无机含碳对离子" in result["standardization_notes"]


@pytest.mark.parametrize(
    "smiles",
    ["CCO.O", "CCO.N", "CCO.O=C=O", "CCO.S=C=S"],
)
def test_neutral_cofragment_is_not_silently_removed(smiles: str) -> None:
    """中性共组分不得被错当为对离子移除。"""
    result = standardize_smiles(smiles)

    assert result["structure_category"] != "modelable"
    assert "中性共组分" in result["standardization_notes"]


def test_charged_counterion_can_be_removed() -> None:
    """有机离子盐中的带电对离子仍可自动移除。"""
    result = standardize_smiles("C[N+](C)(C)C.[Cl-]")

    assert result["rdkit_mol_ok"]
    assert result["structure_category"] == "modelable"
    assert "已移除对离子" in result["standardization_notes"]


@pytest.mark.parametrize(
    "smiles",
    ["[cH-]1cccc1", "[Na+].[cH-]1cccc1", "C[N+](C)(C)C.[cH-]1cccc1"],
)
def test_cyclopentadienyl_is_not_classified_as_carbide(smiles: str) -> None:
    """环戊二烯基负离子不得被自动归类为碳化物。"""
    result = standardize_smiles(smiles)

    assert "碳化物或金属乙炔化物" not in result[
        "standardization_notes"
    ]


@pytest.mark.parametrize(
    "smiles",
    [
        "CCO.[Cl-]",
        "C[N+](C)(C)C.[Na+]",
        "CCO.O=C([O-])O",
        "C[N+](C)(C)CC[N+](C)(C)C.[Cl-]",
    ],
)
def test_unbalanced_or_same_charge_fragments_are_rejected(smiles: str) -> None:
    """中性 parent、同号离子或未配平结构不得自动去盐。"""
    result = standardize_smiles(smiles)

    assert not result["rdkit_mol_ok"]
    assert result["structure_category"] == "excluded"
    assert "无法确认对离子" in result["standardization_notes"]


def test_excluded_solvate_retains_leakage_connectivity_key() -> None:
    """开发集溶剂化物中的有机组分应继续拦截外部集 parent。"""
    solvate = standardize_smiles("CCO.O")
    ethanol = standardize_smiles("CCO")
    records = pd.DataFrame(
        [
            {
                "dataset_role": "development",
                "rdkit_parse_ok": solvate["rdkit_parse_ok"],
                "leakage_connectivity_keys_json": solvate[
                    "leakage_connectivity_keys_json"
                ],
            }
        ]
    )

    keys = collect_leakage_connectivity_keys(records, "development")

    assert not solvate["rdkit_mol_ok"]
    assert ethanol["connectivity_key"] in keys


def test_manual_inorganic_decisions_are_applied(tmp_path: Path) -> None:
    """人工纳入和排除决策应可重现地改变结构类别。"""
    include = standardize_smiles("C=O")
    exclude = standardize_smiles("N#CC#N")
    structures = pd.DataFrame([include, exclude])
    decisions_path = tmp_path / "decisions.csv"
    pd.DataFrame(
        [
            {
                "standard_inchikey": include["standard_inchikey"],
                "decision": "include",
                "review_reason": "确认为有机化合物",
                "reviewer": "审核员甲",
            },
            {
                "standard_inchikey": exclude["standard_inchikey"],
                "decision": "exclude",
                "review_reason": "确认为无机边界结构",
                "reviewer": "审核员乙",
            },
        ]
    ).to_csv(decisions_path, index=False)

    result, decisions = apply_inorganic_carbon_decisions(
        structures, decisions_path
    )

    categories = result.set_index("standard_inchikey")["structure_category"]
    assert categories[include["standard_inchikey"]] == "modelable"
    assert categories[exclude["standard_inchikey"]] == "manual_excluded"
    assert len(decisions) == 2


def test_unknown_manual_inorganic_decision_is_rejected(tmp_path: Path) -> None:
    """人工决策不得引用当前审核集之外的结构。"""
    structures = pd.DataFrame([standardize_smiles("C=O")])
    decisions_path = tmp_path / "decisions.csv"
    pd.DataFrame(
        [
            {
                "standard_inchikey": "UNKNOWN-INCHIKEY",
                "decision": "include",
                "review_reason": "测试",
                "reviewer": "审核员",
            }
        ]
    ).to_csv(decisions_path, index=False)

    with pytest.raises(ValueError, match="未出现在当前"):
        apply_inorganic_carbon_decisions(structures, decisions_path)


def test_review_candidates_are_split_by_dataset_role() -> None:
    """开发集与外部集弱证据候选必须分文件输出。"""
    uncertain = pd.DataFrame(
        [
            {"dataset_role": "development", "label_candidate": "positive"},
            {"dataset_role": "external", "label_candidate": "negative"},
            {"dataset_role": "external", "label_candidate": ""},
        ]
    )

    development, external = split_review_candidates(uncertain)

    assert len(development) == 1
    assert len(external) == 1
    assert development["dataset_role"].eq("development").all()
    assert external["dataset_role"].eq("external").all()


def test_ccris_excluded_only_check_uses_external_scope_only() -> None:
    """CCRIS excluded-only 检查不得因 development uncertain 共享 InChIKey 而误报。"""
    external_valid = pd.DataFrame(
        [{"standard_inchikey": "SHARED", "label_category": "excluded"}]
    )
    external_all = pd.DataFrame(columns=COMPOUND_COLUMNS)

    validate_ccris_excluded_only_keys(external_valid, external_all)

    invalid_external_all = pd.DataFrame(
        [{"standard_inchikey": "SHARED"}]
    )
    with pytest.raises(AssertionError, match="外部聚合集"):
        validate_ccris_excluded_only_keys(external_valid, invalid_external_all)


def test_formal_run_accepts_matching_audit_fingerprint(tmp_path: Path) -> None:
    """正式运行应接受输入指纹一致的审计批次。"""
    audit_config = CleaningConfig(root=tmp_path, dry_run=True)
    fingerprint = cleaning_input_fingerprint(audit_config)
    run_id = "20260101_000000_000000_UTC_test"
    audit_dir = tmp_path / "reports" / "cleaning" / "audits" / run_id
    audit_dir.mkdir(parents=True)
    manifest = build_cleaning_manifest(
        audit_config, run_id=run_id, input_fingerprint=fingerprint
    )
    (audit_dir / "cleaning_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    formal_config = CleaningConfig(
        root=tmp_path, dry_run=False, approved_audit_run=run_id
    )

    validated = validate_approved_audit(formal_config, fingerprint)

    assert validated["run_id"] == run_id


def test_formal_run_rejects_mismatched_audit_fingerprint(tmp_path: Path) -> None:
    """正式运行必须拒绝输入指纹已变化的审计批次。"""
    audit_config = CleaningConfig(root=tmp_path, dry_run=True)
    fingerprint = cleaning_input_fingerprint(audit_config)
    run_id = "20260101_000000_000000_UTC_test"
    audit_dir = tmp_path / "reports" / "cleaning" / "audits" / run_id
    audit_dir.mkdir(parents=True)
    manifest = build_cleaning_manifest(
        audit_config, run_id=run_id, input_fingerprint=fingerprint
    )
    (audit_dir / "cleaning_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    formal_config = CleaningConfig(
        root=tmp_path, dry_run=False, approved_audit_run=run_id
    )

    with pytest.raises(ValueError, match="已变更"):
        validate_approved_audit(formal_config, "不匹配的指纹")


def test_entry_script_is_part_of_cleaning_fingerprint(tmp_path: Path) -> None:
    """入口脚本变化必须使清洗输入指纹失效。"""
    script_path = tmp_path / "scripts" / "clean_datasets.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("# 版本一\n", encoding="utf-8")
    config = CleaningConfig(root=tmp_path, dry_run=True)
    first = cleaning_input_fingerprint(config)

    script_path.write_text("# 版本二\n", encoding="utf-8")
    second = cleaning_input_fingerprint(config)

    assert first != second


def test_formal_run_rejects_mismatched_runtime_signature(tmp_path: Path) -> None:
    """正式运行必须拒绝运行环境签名不一致的审计批次。"""
    audit_config = CleaningConfig(root=tmp_path, dry_run=True)
    fingerprint = cleaning_input_fingerprint(audit_config)
    run_id = "20260101_000000_000000_UTC_test"
    audit_dir = tmp_path / "reports" / "cleaning" / "audits" / run_id
    audit_dir.mkdir(parents=True)
    manifest = build_cleaning_manifest(
        audit_config, run_id=run_id, input_fingerprint=fingerprint
    )
    manifest["runtime_signature"]["rdkit"] = "不匹配的版本"
    (audit_dir / "cleaning_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    formal_config = CleaningConfig(
        root=tmp_path, dry_run=False, approved_audit_run=run_id
    )

    with pytest.raises(ValueError, match="运行环境"):
        validate_approved_audit(formal_config, fingerprint)


def test_manifest_records_runtime_and_output_hashes(tmp_path: Path) -> None:
    """审计清单应记录运行环境与拟发布 CSV 哈希。"""
    outputs = {"train.csv": pd.DataFrame([{"compound_id": "A"}])}
    output_dir = tmp_path / "outputs"
    write_csv(outputs["train.csv"], output_dir / "train.csv")
    output_files = output_file_manifest(outputs, output_dir)
    config = CleaningConfig(root=tmp_path, dry_run=True)

    manifest = build_cleaning_manifest(
        config,
        run_id="test",
        input_fingerprint="fingerprint",
        output_files=output_files,
    )

    assert manifest["runtime_signature"] == runtime_signature()
    assert manifest["output_files"]["train.csv"]["rows"] == 1
    assert len(manifest["output_files"]["train.csv"]["sha256"]) == 64


def test_formal_output_hash_mismatch_is_rejected() -> None:
    """正式输出的哈希或行数不同时必须拒绝提交。"""
    approved = {
        "output_files": {"train.csv": {"sha256": "old", "rows": 1}}
    }
    current = {"train.csv": {"sha256": "new", "rows": 1}}

    with pytest.raises(ValueError, match="哈希或行数变化"):
        validate_output_file_manifest(approved, current)


def make_audit_artifact_fixture(
    tmp_path: Path,
) -> tuple[CleaningConfig, dict[str, object], Path]:
    """创建用于篡改检查的最小审计工件集。"""
    run_id = "20260101_000000_000000_UTC_test"
    audit_dir = tmp_path / "reports" / "cleaning" / "audits" / run_id
    datasets_dir = audit_dir / "datasets"
    write_csv(pd.DataFrame([{"compound_id": "A"}]), datasets_dir / "train.csv")
    write_csv(pd.DataFrame([{"label": "positive"}]), audit_dir / "label_report.csv")
    (audit_dir / "cleaning_log.md").write_text("审计日志\n", encoding="utf-8")
    audit_config = CleaningConfig(root=tmp_path, dry_run=True)
    manifest = build_cleaning_manifest(
        audit_config,
        run_id=run_id,
        input_fingerprint="fingerprint",
        output_files=csv_directory_manifest(datasets_dir),
        report_files=csv_directory_manifest(audit_dir),
        support_files={
            "cleaning_log.md": {
                "sha256": sha256(audit_dir / "cleaning_log.md")
            }
        },
    )
    formal_config = CleaningConfig(
        root=tmp_path, dry_run=False, approved_audit_run=run_id
    )
    return formal_config, manifest, audit_dir


def test_tampered_audit_dataset_is_rejected(tmp_path: Path) -> None:
    """审计数据集被修改后，正式运行前必须拒绝。"""
    config, manifest, audit_dir = make_audit_artifact_fixture(tmp_path)
    (audit_dir / "datasets" / "train.csv").write_text(
        "compound_id\nTAMPERED\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="审计数据工件"):
        validate_audit_artifacts(config, manifest)


def test_tampered_audit_report_is_rejected(tmp_path: Path) -> None:
    """人工审核依赖的报告 CSV 被修改后必须拒绝。"""
    config, manifest, audit_dir = make_audit_artifact_fixture(tmp_path)
    (audit_dir / "label_report.csv").write_text(
        "label\ntampered\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="审计报告工件"):
        validate_audit_artifacts(config, manifest)


def test_tampered_audit_log_is_rejected(tmp_path: Path) -> None:
    """审计日志被修改后必须拒绝正式运行。"""
    config, manifest, audit_dir = make_audit_artifact_fixture(tmp_path)
    (audit_dir / "cleaning_log.md").write_text("已篡改\n", encoding="utf-8")

    with pytest.raises(ValueError, match="审计辅助工件"):
        validate_audit_artifacts(config, manifest)


def test_runtime_signature_uses_actual_inchi_library_version() -> None:
    """环境签名应在新旧 RDKit 中都记录可验证的 InChI 库版本。"""
    library_version = inchi_library_version()

    assert library_version
    assert runtime_signature()["inchi_library_version"] == library_version
    assert runtime_signature()["inchi_implementation_sha256"]
    version_getter = getattr(Chem, "GetInchiVersion", None)
    if callable(version_getter):
        assert library_version == str(version_getter()).strip()
    else:
        assert "InChI version" in library_version
        assert "Software" in library_version


def test_inchi_version_fallback_for_old_rdkit(monkeypatch: pytest.MonkeyPatch) -> None:
    """固定测试旧版 RDKit 无 GetInchiVersion API 时的日志解析分支。"""
    monkeypatch.setattr(Chem, "GetInchiVersion", None, raising=False)

    value = inchi_library_version()

    assert "InChI version" in value
    assert "Software" in value


def test_external_rdkit_inchi_libraries_are_fingerprinted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """跨平台模拟 Linux wheel 布局，确认同级 rdkit.libs 动态库纳入指纹。"""
    rdkit_root = tmp_path / "site-packages" / "rdkit"
    chem_dir = rdkit_root / "Chem"
    external_library_dir = rdkit_root.parent / "rdkit.libs"
    chem_dir.mkdir(parents=True)
    external_library_dir.mkdir()
    fake_extension = chem_dir / "rdinchi.so"
    fake_extension.write_bytes(b"rdinchi-extension")
    linked_libraries = {
        external_library_dir / "libRDKitInchi-test.so.1",
        external_library_dir / "libRDKitRDInchiLib-test.so.1",
    }
    for path in linked_libraries:
        path.write_bytes(path.name.encode("utf-8"))
    monkeypatch.setattr(Chem, "__file__", str(chem_dir / "__init__.py"))
    monkeypatch.setattr(rdinchi, "__file__", str(fake_extension))

    discovered = inchi_binary_paths()

    assert fake_extension.resolve() in discovered
    assert {path.resolve() for path in linked_libraries} <= discovered


def write_synthetic_cleaning_inputs(root: Path) -> None:
    """写入只用于端到端工程保护测试的最小原始表。"""
    raw_dir = root / "data" / "raw"
    raw_dir.mkdir(parents=True)
    smiles_values = ["C" * length for length in range(2, 12)]
    cpdb_rows = []
    structure_rows = []
    for index, smiles in enumerate(smiles_values, start=1):
        chemical_id = f"CHEM-{index}"
        cpdb_rows.append(
            {
                "idnum": f"REC-{index}",
                "chemcode": chemical_id,
                "name": chemical_id,
                "cas": "",
                "opinion": "+" if index <= 5 else "-",
                "inad": "",
                "species": "rat",
                "route": "oral",
                "papernum": f"REF-{index}",
            }
        )
        structure_rows.append(
            {
                "source": "cpdb",
                "source_record_id": chemical_id,
                "source_smiles": smiles,
                "structure_status": "ok",
            }
        )
    pd.DataFrame(cpdb_rows).to_csv(raw_dir / "cpdb_raw.csv", index=False)
    pd.DataFrame(structure_rows).to_csv(
        raw_dir / "cpdb_structures_raw.csv", index=False
    )
    pd.DataFrame(
        columns=["CHEMICAL NAME", "CASRN", "DTXSID", "WOE DETAILS JSON"]
    ).to_csv(raw_dir / "iris_raw.csv", index=False)
    pd.DataFrame(
        columns=[
            "DOCNO",
            "NameOfSubstance",
            "CASRegistryNumber",
            "carcinogenicity_studies_json",
        ]
    ).to_csv(raw_dir / "ccris_raw.csv", index=False)
    empty_structure_columns = [
        "source",
        "source_record_id",
        "source_smiles",
        "structure_status",
    ]
    for source in ("iris", "ccris"):
        pd.DataFrame(columns=empty_structure_columns).to_csv(
            raw_dir / f"{source}_structures_raw.csv", index=False
        )


def test_dry_run_artifact_validation_and_formal_chain(tmp_path: Path) -> None:
    """合成数据应完成 dry-run、工件校验和 formal，篡改后必须失败。"""
    write_synthetic_cleaning_inputs(tmp_path)
    run_cleaning(CleaningConfig(root=tmp_path, dry_run=True))
    audit_root = tmp_path / "reports" / "cleaning" / "audits"
    run_ids = [path.name for path in audit_root.iterdir() if path.is_dir()]
    assert len(run_ids) == 1
    formal_config = CleaningConfig(
        root=tmp_path, dry_run=False, approved_audit_run=run_ids[0]
    )

    run_cleaning(formal_config)

    assert (tmp_path / "data" / "processed" / "train.csv").is_file()
    audit_train = audit_root / run_ids[0] / "datasets" / "train.csv"
    audit_train.write_text("compound_id\n已篡改\n", encoding="utf-8")
    with pytest.raises(ValueError, match="审计数据工件"):
        run_cleaning(formal_config)


def test_all_empty_sources_raise_clear_error(tmp_path: Path) -> None:
    """六个原始表都只有表头时应保留结构模式并报出明确错误。"""
    write_synthetic_cleaning_inputs(tmp_path)
    raw_dir = tmp_path / "data" / "raw"
    pd.DataFrame(
        columns=[
            "idnum",
            "chemcode",
            "name",
            "cas",
            "opinion",
            "inad",
            "species",
            "route",
            "papernum",
        ]
    ).to_csv(raw_dir / "cpdb_raw.csv", index=False)
    pd.DataFrame(
        columns=["source", "source_record_id", "source_smiles", "structure_status"]
    ).to_csv(raw_dir / "cpdb_structures_raw.csv", index=False)
    manual_dir = tmp_path / "data" / "manual"
    manual_dir.mkdir()
    pd.DataFrame(
        [
            {
                "standard_inchikey": "UNKNOWN",
                "decision": "include",
                "review_reason": "测试错误优先级",
                "reviewer": "测试人",
            }
        ]
    ).to_csv(manual_dir / "inorganic_carbon_decisions.csv", index=False)

    structures = standardize_structure_tables(raw_dir)

    assert structures.empty
    assert "inorganic_carbon_review_required" in structures.columns
    with pytest.raises(ValueError, match="所有来源数据均为空"):
        run_cleaning(CleaningConfig(root=tmp_path, dry_run=True))


def test_duplicate_source_record_ids_are_rejected() -> None:
    """来源内重复的证据记录 ID 必须报错，不得静默去重。"""
    records = pd.DataFrame(
        [
            {
                "source": "cpdb",
                "source_record_id": "1",
                "source_chemical_id": "abc",
                "label_raw": "+",
                "label_category": "positive",
            },
            {
                "source": "cpdb",
                "source_record_id": "1",
                "source_chemical_id": "abc",
                "label_raw": "-",
                "label_category": "negative",
            },
        ]
    )

    with pytest.raises(ValueError, match="重复的来源记录 ID"):
        validate_source_record_ids(records)


def test_scaffold_split_keeps_acyclic_connectivity_groups_together() -> None:
    """scaffold 划分不得拆分同一连接结构的无环化合物。"""
    rows = []
    for group_index in range(10):
        for stereo_index in range(2):
            rows.append(
                {
                    "standard_inchikey": f"FULL-{group_index}-{stereo_index}",
                    "connectivity_key": f"CONNECTIVITY-{group_index}",
                    "murcko_scaffold": "",
                    "label_binary": group_index % 2,
                }
            )
    development = pd.DataFrame(rows)
    config = CleaningConfig(
        root=ROOT,
        split_method="scaffold",
        validation_size=0.2,
        random_seed=0,
    )

    train, validation = split_development(development, config)

    assert not set(train["connectivity_key"]) & set(validation["connectivity_key"])


def test_cyclic_stereoisomers_share_scaffold_connectivity_group() -> None:
    """有环立体异构体不得因骨架立体表示而被分到不同候选组。"""
    left = standardize_smiles("C1CC[C@@H]2CCC[C@H]2C1")
    right = standardize_smiles("C1CC[C@H]2CCC[C@@H]2C1")
    development = pd.DataFrame(
        [
            {
                "connectivity_key": left["connectivity_key"],
                "murcko_scaffold": left["murcko_scaffold"],
            },
            {
                "connectivity_key": right["connectivity_key"],
                "murcko_scaffold": right["murcko_scaffold"],
            },
        ]
    )

    groups = scaffold_connectivity_groups(development)

    assert left["connectivity_key"] == right["connectivity_key"]
    assert left["murcko_scaffold"] == right["murcko_scaffold"]
    assert groups.nunique() == 1
