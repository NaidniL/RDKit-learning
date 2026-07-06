"""阶段 2 阻断集、泄漏与互变异构体审计测试。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.enums import (  # noqa: E402
    DatasetRole,
    ExactDuplicateClass,
    LabelStatus,
    LeakageStatus,
    ReviewStatus,
)
from modeling_dataset.leakage import build_leakage  # noqa: E402
from modeling_dataset.role_resolution import CoreRoleResolution  # noqa: E402


KEY_A = "AAAAAAAAAAAAAA-BBBBBBBBBB-N"
KEY_B = "AAAAAAAAAAAAAA-CCCCCCCCCC-N"
KEY_C = "DDDDDDDDDDDDDD-EEEEEEEEEE-N"


def _resolution(compound_id: str, role: DatasetRole) -> CoreRoleResolution:
    return CoreRoleResolution(
        compound_id=compound_id,
        dataset_role=role,
        role_normalized_label=1,
        label_status=LabelStatus.CLEAR_POSITIVE,
        review_status=ReviewStatus.NOT_REQUIRED,
        resolution_keys=(f"REC:{compound_id}:{role.value}",),
        nonresolution_keys=(),
        resolution_sources=("cpdb" if role is DatasetRole.DEVELOPMENT else "ccris",),
        source_labels=("positive",),
        endpoint_only=False,
        clear_positive_count=1,
        clear_negative_count=0,
        nonbinary_count=0,
        discordant_nonclear_count=0,
        has_discordant_nonclear_evidence=False,
        exact_duplicate_class=ExactDuplicateClass.SINGLE_RECORD,
        structure_status="eligible",
        structure_reasons=(),
    )


def test_block_sets_leakage_precedence_and_tautomer_sensitivity(
    tmp_path: Path,
) -> None:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "excluded_set.csv").write_text(
        "source,dataset_role,source_record_id,leakage_connectivity_keys_json\n"
        'cpdb,development,dev-1,"[""ZZZZZZZZZZZZZZ""]"\n'
        'ccris,external,ext-1,"[""YYYYYYYYYYYYYY""]"\n',
        encoding="utf-8",
        newline="",
    )
    (processed / "external_ccris_test.csv").write_text(
        "standard_inchikey,dataset_role,label_binary\n"
        f"{KEY_C},external,1\n",
        encoding="utf-8",
        newline="",
    )
    dev_id = f"CMP:{KEY_A}"
    connectivity_id = f"CMP:{KEY_B}"
    clear_id = f"CMP:{KEY_C}"
    records = [
        {
            "record_key": "REC:dev",
            "source_dataset": "cpdb",
            "source_record_id": "dev-1",
            "standard_inchikey": KEY_A,
            "dataset_role": "development",
            "leakage_connectivity_keys_json": '["ZZZZZZZZZZZZZZ"]',
        }
    ]
    compounds = [
        {
            "compound_id": dev_id,
            "standardized_inchikey": KEY_A,
            "connectivity_key": "AAAAAAAAAAAAAA",
            "tautomer_family_key": "TAUTOMER-1",
            "structure_status": "eligible",
        },
        {
            "compound_id": connectivity_id,
            "standardized_inchikey": KEY_B,
            "connectivity_key": "AAAAAAAAAAAAAA",
            "tautomer_family_key": "TAUTOMER-2",
            "structure_status": "eligible",
        },
        {
            "compound_id": clear_id,
            "standardized_inchikey": KEY_C,
            "connectivity_key": "DDDDDDDDDDDDDD",
            "tautomer_family_key": "TAUTOMER-1",
            "structure_status": "eligible",
        },
    ]
    result = build_leakage(
        tmp_path,
        records,
        compounds,
        [
            _resolution(dev_id, DatasetRole.DEVELOPMENT),
            _resolution(connectivity_id, DatasetRole.EXTERNAL),
            _resolution(clear_id, DatasetRole.EXTERNAL),
        ],
    )

    assert result.exact_block_keys == {KEY_A}
    assert result.connectivity_block_keys == {
        "AAAAAAAAAAAAAA",
        "ZZZZZZZZZZZZZZ",
    }
    assert "YYYYYYYYYYYYYY" not in result.connectivity_block_keys
    assert result.role_statuses[(connectivity_id, "external")] is (
        LeakageStatus.CONNECTIVITY_OVERLAP
    )
    assert result.role_statuses[(clear_id, "external")] is LeakageStatus.CLEAR
    assert result.primary_external_ids == {clear_id}
    assert result.tautomer_overlap_ids == {clear_id}
    assert result.sensitivity_external_ids == set()
    assert result.tautomer_overlap_rows[0]["development_compound_ids_json"] == [
        dev_id
    ]


def test_full_leakage_regression() -> None:
    from modeling_dataset.core_pipeline import validate_core

    result = validate_core(ROOT)
    assert len(result.leakage.exact_block_keys) == 1493
    assert len(result.leakage.connectivity_block_keys) == 1638
    assert len(result.leakage.primary_external_ids) == 455
    assert len(result.leakage.sensitivity_external_ids) == 455
    assert len(result.leakage.tautomer_overlap_ids) == 1182
    assert sum(
        value is LeakageStatus.EXACT_OVERLAP
        for value in result.leakage.role_statuses.values()
    ) == 1120
    assert sum(
        value is LeakageStatus.CONNECTIVITY_OVERLAP
        for value in result.leakage.role_statuses.values()
    ) == 141
