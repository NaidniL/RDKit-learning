"""确定性序列化和 golden bytes 测试。"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.schema_registry import (  # noqa: E402
    ArtifactClass,
    ArtifactFormat,
    ArtifactSchema,
    FieldType,
    SCHEMA_REGISTRY,
    field,
)
from modeling_dataset.serialization import (  # noqa: E402
    canonical_json,
    canonical_json_array,
    digest_bytes,
    logical_csv_row_count,
    serialize_csv,
    serialize_float,
    validate_canonical_json_text,
)


GOLDEN_SCHEMA = ArtifactSchema(
    path="reports/golden.csv",
    artifact_class=ArtifactClass.RELEASE,
    artifact_format=ArtifactFormat.CSV,
    fields=(
        field("dataset_role", enum_name="DatasetRole"),
        field("identifier"),
        field("value", FieldType.FLOAT),
        field("enabled", FieldType.BOOLEAN),
        field("items", FieldType.JSON, canonical_array=True),
        field("note", nullable=True),
    ),
    unique_key=("dataset_role", "identifier"),
    sort_key=("dataset_role", "identifier"),
)


def test_canonical_json_and_hash_are_stable() -> None:
    left = canonical_json({"β": 2, "a": {"y": 1, "x": 0}})
    right = canonical_json({"a": {"x": 0, "y": 1}, "β": 2})
    assert left == right == '{"a":{"x":0,"y":1},"β":2}'
    assert digest_bytes(left.encode())[0] == digest_bytes(right.encode())[0]


def test_canonical_json_array_rejects_unsorted_or_duplicate_values() -> None:
    assert canonical_json_array(["a", "b"]) == '["a","b"]'
    with pytest.raises(ValueError, match="未按"):
        canonical_json_array(["b", "a"])
    with pytest.raises(ValueError, match="重复"):
        canonical_json_array(["a", "a"])
    with pytest.raises(ValueError, match="不是 canonical"):
        validate_canonical_json_text('["a", "b"]', canonical_array=True)


def test_float_boolean_missing_and_carriage_return_rules() -> None:
    assert serialize_float(-0.0) == "0"
    assert serialize_float(1.25) == "1.25"
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="NaN 或 Infinity"):
            serialize_float(value)
    rows = [
        {
            "dataset_role": "development",
            "identifier": "A",
            "value": -0.0,
            "enabled": True,
            "items": ["a", "b"],
            "note": None,
        }
    ]
    assert b"development,A,0,true" in serialize_csv(rows, GOLDEN_SCHEMA)
    rows[0]["note"] = "bad\rtext"
    with pytest.raises(ValueError, match="回车符"):
        serialize_csv(rows, GOLDEN_SCHEMA)


def test_golden_csv_is_sorted_by_enum_rank_and_row_order_independent() -> None:
    rows = [
        {
            "dataset_role": "external",
            "identifier": "B",
            "value": 2.0,
            "enabled": False,
            "items": ["b"],
            "note": "外部",
        },
        {
            "dataset_role": "development",
            "identifier": "A",
            "value": -0.0,
            "enabled": True,
            "items": ["a", "b"],
            "note": "第一行\n第二行",
        },
    ]
    expected = (
        "dataset_role,identifier,value,enabled,items,note\n"
        'development,A,0,true,"[""a"",""b""]","第一行\n第二行"\n'
        'external,B,2,false,"[""b""]",外部\n'
    ).encode("utf-8")
    assert serialize_csv(rows, GOLDEN_SCHEMA) == expected
    assert serialize_csv(reversed(rows), GOLDEN_SCHEMA) == expected
    assert not expected.startswith(b"\xef\xbb\xbf")
    assert expected.endswith(b"\n")


def test_split_aliases_use_query_split_rank() -> None:
    schema = SCHEMA_REGISTRY["reports/split_summary.csv"]
    rows = [
        {
            "split": split,
            "sample_count": 0,
            "positive_count": 0,
            "negative_count": 0,
            "positive_rate": None,
        }
        for split in (
            "external_test",
            "validation",
            "external_tautomer_sensitivity",
            "train",
        )
    ]
    text = serialize_csv(rows, schema).decode("utf-8")
    assert [line.split(",", 1)[0] for line in text.splitlines()[1:]] == [
        "train",
        "validation",
        "external_test",
        "external_tautomer_sensitivity",
    ]


def test_logical_csv_row_count_handles_multiline_fields(tmp_path: Path) -> None:
    payload = serialize_csv(
        [
            {
                "dataset_role": "development",
                "identifier": "00123",
                "value": 1.0,
                "enabled": True,
                "items": [],
                "note": "一\n二",
            },
            {
                "dataset_role": "development",
                "identifier": "123",
                "value": 2.0,
                "enabled": False,
                "items": [],
                "note": "",
            },
        ],
        GOLDEN_SCHEMA,
    )
    path = tmp_path / "multiline.csv"
    path.write_bytes(payload)
    assert logical_csv_row_count(path) == 2
    assert payload.count(b"\n") > 3
    assert b"00123" in payload and b",123," in payload


def test_cross_role_pair_serialization_is_order_independent() -> None:
    schema = SCHEMA_REGISTRY["reports/label_discordant_near_neighbors.csv"]
    base = {
        "comparison_scope": "cross_role",
        "compound_id_a": "CMP:A",
        "compound_id_b": "CMP:B",
        "relation_type": "high_similarity",
        "similarity": 0.9,
        "label_a": 1,
        "label_b": 0,
        "label_relation": "opposite",
    }
    rows = [
        {
            **base,
            "dataset_role_a": "development",
            "dataset_role_b": "external",
        },
        {
            **base,
            "dataset_role_a": "external",
            "dataset_role_b": "development",
        },
    ]
    assert serialize_csv(rows, schema) == serialize_csv(reversed(rows), schema)
