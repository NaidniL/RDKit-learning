"""确定性 JSON、CSV 和文件摘要序列化。"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .enums import ControlledStringEnum, ENUM_RANKS, ENUM_TYPES
from .schema_registry import ArtifactFormat, ArtifactSchema, FieldSpec, FieldType


@dataclass(frozen=True)
class FileDigest:
    sha256: str
    bytes: int
    rows: int | None = None


def _reject_carriage_return(value: Any) -> None:
    if isinstance(value, str) and "\r" in value:
        raise ValueError("字符串包含禁止的回车符 \\r")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_carriage_return(key)
            _reject_carriage_return(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_carriage_return(item)


def _reject_nonfinite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON 和 CSV 禁止 NaN 或 Infinity")
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_nonfinite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_nonfinite(item)


def canonical_json(value: Any) -> str:
    """生成 UTF-8 语义下的 compact canonical JSON。"""

    _reject_carriage_return(value)
    _reject_nonfinite(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_json_bytes(value: Any, *, terminal_lf: bool = True) -> bytes:
    suffix = "\n" if terminal_lf else ""
    return (canonical_json(value) + suffix).encode("utf-8")


def canonical_json_array(values: Sequence[Any]) -> str:
    """只接受已经去重并按 canonical JSON 排序的数组。"""

    keys = [canonical_json(value) for value in values]
    if len(keys) != len(set(keys)):
        raise ValueError("canonical JSON 数组包含重复元素")
    if keys != sorted(keys):
        raise ValueError("canonical JSON 数组未按 Unicode/canonical JSON 排序")
    return canonical_json(list(values))


def validate_canonical_json_text(text: str, *, canonical_array: bool = False) -> Any:
    """验证 JSON 文本已经采用项目 canonical 表示。"""

    _reject_carriage_return(text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 字段解析失败：{exc}") from exc
    expected = canonical_json(value)
    if text != expected:
        raise ValueError("JSON 字段不是 canonical JSON")
    if canonical_array:
        if not isinstance(value, list):
            raise ValueError("字段必须是 canonical JSON 数组")
        canonical_json_array(value)
    return value


def serialize_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("浮点值禁止 NaN 或 Infinity")
    if value == 0.0:
        return "0"
    return format(value, ".17g")


def serialize_scalar(value: Any, spec: FieldSpec) -> str:
    """按字段 schema 将单值序列化为 CSV 文本。"""

    if value is None or value == "":
        if spec.nullable:
            return ""
        raise ValueError(f"字段 {spec.name} 不允许为空")
    if isinstance(value, ControlledStringEnum):
        value = value.value
    if spec.enum_name is not None:
        enum_type = ENUM_TYPES.get(spec.enum_name)
        if enum_type is None:
            raise ValueError(f"未注册枚举类型：{spec.enum_name}")
        enum_type.parse(str(value))
    if spec.field_type is FieldType.JSON:
        if isinstance(value, str):
            validate_canonical_json_text(value, canonical_array=spec.canonical_array)
            return value
        if spec.canonical_array:
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"字段 {spec.name} 必须是 JSON 数组")
            return canonical_json_array(list(value))
        return canonical_json(value)
    if spec.field_type is FieldType.BOOLEAN:
        if type(value) is not bool:
            raise ValueError(f"字段 {spec.name} 必须是布尔值")
        return "true" if value else "false"
    if spec.field_type is FieldType.INTEGER:
        if type(value) is not int:
            raise ValueError(f"字段 {spec.name} 必须是整数")
        _validate_numeric_range(float(value), spec)
        return str(value)
    if spec.field_type is FieldType.FLOAT:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"字段 {spec.name} 必须是有限浮点数")
        numeric = float(value)
        _validate_numeric_range(numeric, spec)
        return serialize_float(numeric)
    if not isinstance(value, str):
        raise ValueError(f"字段 {spec.name} 必须是字符串")
    _reject_carriage_return(value)
    return value


def _validate_numeric_range(value: float, spec: FieldSpec) -> None:
    if spec.numeric_min is not None and value < spec.numeric_min:
        raise ValueError(f"字段 {spec.name} 小于最小值 {spec.numeric_min}")
    if spec.numeric_max is not None and value > spec.numeric_max:
        raise ValueError(f"字段 {spec.name} 大于最大值 {spec.numeric_max}")


def parse_csv_scalar(text: str, spec: FieldSpec) -> Any:
    """按 schema 解析并验证 canonical CSV 单值。"""

    if text == "":
        if spec.nullable:
            return None
        raise ValueError(f"字段 {spec.name} 不允许为空")
    if "\r" in text:
        raise ValueError(f"字段 {spec.name} 包含禁止的回车符")
    if spec.field_type is FieldType.BOOLEAN:
        if text not in {"true", "false"}:
            raise ValueError(f"字段 {spec.name} 不是 canonical 布尔值")
        return text == "true"
    if spec.field_type is FieldType.INTEGER:
        if text == "0":
            integer_value = 0
        elif text.startswith("-") and text[1:].isdigit() and not text.startswith("-0"):
            integer_value = int(text)
        elif text.isdigit() and not text.startswith("0"):
            integer_value = int(text)
        else:
            raise ValueError(f"字段 {spec.name} 不是 canonical 整数")
        _validate_numeric_range(float(integer_value), spec)
        return integer_value
    if spec.field_type is FieldType.FLOAT:
        try:
            float_value = float(text)
        except ValueError as exc:
            raise ValueError(f"字段 {spec.name} 不是浮点数") from exc
        if serialize_float(float_value) != text:
            raise ValueError(f"字段 {spec.name} 不是 .17g canonical 浮点")
        _validate_numeric_range(float_value, spec)
        return float_value
    if spec.field_type is FieldType.JSON:
        validate_canonical_json_text(text, canonical_array=spec.canonical_array)
        return text
    serialize_scalar(text, spec)
    return text


def _rank_name(field_name: str) -> str:
    if field_name in {"dataset_role_a", "dataset_role_b"}:
        return "dataset_role"
    if field_name == "nearest_split":
        return "query_split"
    return field_name


def _sort_part(field_name: str, value: Any) -> tuple[int, Any]:
    if isinstance(value, ControlledStringEnum):
        value = value.value
    if value is None or value == "":
        return (2, "")
    rank_map = ENUM_RANKS.get(_rank_name(field_name))
    if rank_map is not None:
        text = str(value)
        if text not in rank_map:
            raise ValueError(f"字段 {field_name} 缺少枚举排序 rank：{text!r}")
        return (0, rank_map[text])
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, (int, float)):
        return (0, value)
    return (0, str(value))


def sort_rows(
    rows: Iterable[Mapping[str, Any]], schema: ArtifactSchema
) -> list[Mapping[str, Any]]:
    """使用 registry sort key 与枚举 rank 排序。"""

    materialized = list(rows)
    return sorted(
        materialized,
        key=lambda row: tuple(
            _sort_part(name, row.get(name)) for name in schema.sort_key
        ),
    )


def serialize_csv(
    rows: Iterable[Mapping[str, Any]], schema: ArtifactSchema
) -> bytes:
    """将记录序列化为固定 dialect 的 UTF-8 CSV。"""

    if schema.artifact_format is not ArtifactFormat.CSV:
        raise ValueError(f"artifact 不是 CSV：{schema.path}")
    ordered_rows = sort_rows(rows, schema)
    from .validation import validate_rows

    validate_rows(ordered_rows, schema)
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.writer(
        buffer,
        delimiter=",",
        quotechar='"',
        doublequote=True,
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )
    writer.writerow(schema.columns)
    for row in ordered_rows:
        if set(row) != set(schema.columns):
            missing = sorted(set(schema.columns) - set(row))
            extra = sorted(set(row) - set(schema.columns))
            raise ValueError(
                f"{schema.path} 行字段不匹配；缺少={missing}，多出={extra}"
            )
        writer.writerow(
            [serialize_scalar(row[spec.name], spec) for spec in schema.fields]
        )
    text = buffer.getvalue()
    if "\r" in text:
        raise ValueError("序列化结果意外包含回车符")
    return text.encode("utf-8")


def write_bytes_fsync(path: Path, payload: bytes) -> None:
    """写入文件并同步到磁盘。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def write_csv(
    path: Path, rows: Iterable[Mapping[str, Any]], schema: ArtifactSchema
) -> FileDigest:
    payload = serialize_csv(rows, schema)
    write_bytes_fsync(path, payload)
    return digest_file(path, csv_rows=True)


def logical_csv_row_count(path: Path) -> int:
    """按 CSV 逻辑记录计数，不按物理 LF 计数。"""

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(
            handle,
            delimiter=",",
            quotechar='"',
            doublequote=True,
            strict=True,
        )
        try:
            next(reader)
        except StopIteration:
            raise ValueError(f"CSV 缺少表头：{path}") from None
        return sum(1 for _ in reader)


def digest_bytes(payload: bytes) -> tuple[str, int]:
    return hashlib.sha256(payload).hexdigest(), len(payload)


def digest_file(path: Path, *, csv_rows: bool = False) -> FileDigest:
    payload = path.read_bytes()
    sha256, byte_count = digest_bytes(payload)
    rows = logical_csv_row_count(path) if csv_rows else None
    return FileDigest(sha256=sha256, bytes=byte_count, rows=rows)
