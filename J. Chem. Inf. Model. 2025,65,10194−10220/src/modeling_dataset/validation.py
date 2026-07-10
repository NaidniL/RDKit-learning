"""与业务聚合无关的通用校验器。"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .enums import (
    ENUM_TYPES,
    DatasetRole,
    ExactDuplicateClass,
    LabelStatus,
    LeakageStatus,
    ReviewStatus,
    SplitEligibility,
    StructureStatus,
)
from .paths import reject_symlink_chain, validate_relative_path
from .schema_registry import (
    ArtifactClass,
    ArtifactFormat,
    ArtifactSchema,
    FieldType,
    SCHEMA_REGISTRY,
)
from .serialization import (
    canonical_json_bytes,
    parse_csv_scalar,
    serialize_csv,
    serialize_scalar,
    validate_canonical_json_text,
)


INCHIKEY_PATTERN = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
UTC_TIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass(frozen=True)
class RoleState:
    dataset_role: DatasetRole
    label_status: LabelStatus
    role_normalized_label: int | None
    review_status: ReviewStatus
    structure_status: StructureStatus
    leakage_status: LeakageStatus
    has_tautomer_overlap: bool
    discordant_nonclear_count: int
    has_discordant_nonclear_evidence: bool
    split_eligibility: SplitEligibility


def validate_columns(actual: Sequence[str], schema: ArtifactSchema) -> None:
    """拒绝多列、少列、错序和重复列。"""

    if len(actual) != len(set(actual)):
        raise ValueError(f"CSV 存在重复列：{list(actual)}")
    expected = list(schema.columns)
    if list(actual) != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ValueError(
            f"{schema.path} 列集合或顺序不一致；缺少={missing}，多出={extra}"
        )


def validate_csv_header(path: Path, schema: ArtifactSchema) -> None:
    if schema.artifact_format is not ArtifactFormat.CSV:
        raise ValueError(f"artifact 不是 CSV：{schema.path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"CSV 为空：{path}") from None
    validate_columns(header, schema)


def validate_unique_key(
    rows: Iterable[Mapping[str, Any]], schema: ArtifactSchema
) -> None:
    seen: set[tuple[Any, ...]] = set()
    for index, row in enumerate(rows, start=1):
        key = tuple(row.get(name) for name in schema.unique_key)
        if any(value is None or value == "" for value in key):
            raise ValueError(f"{schema.path} 第 {index} 行唯一键为空：{key}")
        if key in seen:
            raise ValueError(f"{schema.path} 唯一键重复：{key}")
        seen.add(key)


def validate_row(row: Mapping[str, Any], schema: ArtifactSchema) -> None:
    if set(row) != set(schema.columns):
        raise ValueError(f"{schema.path} 行字段集合不匹配")
    for spec in schema.fields:
        value = row[spec.name]
        serialize_scalar(value, spec)
        if value is None or value == "":
            continue
        if spec.enum_name is not None:
            enum_type = ENUM_TYPES.get(spec.enum_name)
            if enum_type is None:
                raise ValueError(f"未注册枚举类型：{spec.enum_name}")
            enum_type.parse(str(value))
        if spec.field_type is FieldType.JSON and isinstance(value, str):
            validate_canonical_json_text(value, canonical_array=spec.canonical_array)
        if spec.field_type is FieldType.UTC_TIME and not UTC_TIME_PATTERN.fullmatch(
            str(value)
        ):
            raise ValueError(f"UTC 时间格式非法：{value!r}")
        if spec.field_type is FieldType.UTC_TIME:
            try:
                datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ")
            except ValueError as exc:
                raise ValueError(f"UTC 时间日期非法：{value!r}") from exc
        if spec.field_type is FieldType.INCHIKEY and not INCHIKEY_PATTERN.fullmatch(
            str(value)
        ):
            raise ValueError(f"InChIKey 格式非法：{value!r}")


def validate_rows(
    rows: Sequence[Mapping[str, Any]],
    schema: ArtifactSchema,
    *,
    formal: bool = False,
) -> None:
    for row in rows:
        validate_row(row, schema)
    validate_unique_key(rows, schema)
    validate_artifact_semantics(rows, schema, formal=formal)


def expected_split_eligibility(
    dataset_role: DatasetRole,
    label_status: LabelStatus,
    structure_status: StructureStatus,
    leakage_status: LeakageStatus,
) -> SplitEligibility:
    """显式决策表的唯一资格派生入口。"""

    if structure_status is StructureStatus.INELIGIBLE:
        return SplitEligibility.INELIGIBLE_STRUCTURE
    if label_status in {LabelStatus.CONFLICT, LabelStatus.UNCERTAIN}:
        return SplitEligibility.INELIGIBLE_LABEL
    if dataset_role is DatasetRole.EXTERNAL and leakage_status in {
        LeakageStatus.EXACT_OVERLAP,
        LeakageStatus.CONNECTIVITY_OVERLAP,
    }:
        return SplitEligibility.INELIGIBLE_LEAKAGE
    return SplitEligibility.ELIGIBLE


def validate_role_state(state: RoleState, *, formal: bool = False) -> None:
    """校验标签、结构、泄漏、审核和资格的合法组合。"""

    if state.label_status is LabelStatus.CLEAR_POSITIVE:
        if state.role_normalized_label != 1:
            raise ValueError("clear_positive 必须对应标签 1")
    elif state.label_status is LabelStatus.CLEAR_NEGATIVE:
        if state.role_normalized_label != 0:
            raise ValueError("clear_negative 必须对应标签 0")
    elif state.role_normalized_label is not None:
        raise ValueError("conflict/uncertain 的标签必须为空")

    if state.label_status is LabelStatus.CONFLICT:
        allowed_review = {
            ReviewStatus.PENDING,
            ReviewStatus.CONFIRMED_EXCLUDE,
            ReviewStatus.AUTOMATIC_EXCLUDE,
        }
        if state.review_status not in allowed_review:
            raise ValueError("conflict 的 review_status 非法")
        if formal and state.review_status is ReviewStatus.PENDING:
            raise ValueError("正式 release 不允许未裁决的标签冲突")
    elif state.label_status in {LabelStatus.CLEAR_POSITIVE, LabelStatus.CLEAR_NEGATIVE}:
        if state.review_status not in {
            ReviewStatus.NOT_REQUIRED,
            ReviewStatus.AUTOMATIC_RESOLVED,
        }:
            raise ValueError("明确标签的 review_status 非法")
    elif state.review_status is not ReviewStatus.NOT_REQUIRED:
        raise ValueError("非 conflict 行必须使用 review_status=not_required")

    if state.discordant_nonclear_count < 0:
        raise ValueError("discordant_nonclear_count 不能为负数")
    expected_discordant = state.discordant_nonclear_count > 0
    if state.has_discordant_nonclear_evidence is not expected_discordant:
        raise ValueError("discordant nonclear 计数与布尔标志不一致")
    if state.label_status in {LabelStatus.CONFLICT, LabelStatus.UNCERTAIN} and (
        state.discordant_nonclear_count != 0
        or state.has_discordant_nonclear_evidence
    ):
        raise ValueError("conflict/uncertain 不允许 discordant nonclear 计数")
    if type(state.has_tautomer_overlap) is not bool:
        raise ValueError("has_tautomer_overlap 必须是布尔值")

    if state.dataset_role is DatasetRole.DEVELOPMENT:
        if state.leakage_status is not LeakageStatus.NOT_APPLICABLE:
            raise ValueError("development 的 leakage_status 必须是 not_applicable")
        if state.has_tautomer_overlap:
            raise ValueError("development 的 has_tautomer_overlap 必须是 false")
    elif state.leakage_status is LeakageStatus.NOT_APPLICABLE:
        raise ValueError("external 的 leakage_status 不能是 not_applicable")

    expected = expected_split_eligibility(
        state.dataset_role,
        state.label_status,
        state.structure_status,
        state.leakage_status,
    )
    if state.split_eligibility is not expected:
        raise ValueError(
            "状态轴与 split_eligibility 不一致："
            f"期望 {expected.value}，实际 {state.split_eligibility.value}"
        )


def validate_artifact_semantics(
    rows: Sequence[Mapping[str, Any]],
    schema: ArtifactSchema,
    *,
    formal: bool = False,
) -> None:
    """校验依赖多个字段的 artifact 级不变量。"""

    if schema.path == "modeling/compound_role_resolutions.csv":
        for row in rows:
            validate_role_state(
                RoleState(
                    dataset_role=DatasetRole(row["dataset_role"]),
                    label_status=LabelStatus(row["label_status"]),
                    role_normalized_label=row["role_normalized_label"],
                    review_status=ReviewStatus(row["review_status"]),
                    structure_status=StructureStatus(row["structure_status"]),
                    leakage_status=LeakageStatus(row["leakage_status"]),
                    has_tautomer_overlap=row["has_tautomer_overlap"],
                    discordant_nonclear_count=row["discordant_nonclear_count"],
                    has_discordant_nonclear_evidence=row[
                        "has_discordant_nonclear_evidence"
                    ],
                    split_eligibility=SplitEligibility(row["split_eligibility"]),
                ),
                formal=formal,
            )
    if schema.path == "modeling/duplicate_groups.csv":
        for row in rows:
            total = (
                row["clear_positive_count"]
                + row["clear_negative_count"]
                + row["nonbinary_count"]
            )
            if total != row["record_count"]:
                raise ValueError("duplicate group 计数不守恒")
            if row["discordant_nonclear_count"] > row["nonbinary_count"]:
                raise ValueError("discordant_nonclear_count 超过 nonbinary_count")
            if row["has_discordant_nonclear_evidence"] is not (
                row["discordant_nonclear_count"] > 0
            ):
                raise ValueError("duplicate group discordant 标志与计数不一致")
            if row["record_count"] == 1:
                expected_class = ExactDuplicateClass.SINGLE_RECORD
            elif row["clear_positive_count"] > 0 and row[
                "clear_negative_count"
            ] > 0:
                expected_class = ExactDuplicateClass.MULTIPLE_CLEAR_CONFLICTING
            elif (
                row["clear_positive_count"] > 0
                or row["clear_negative_count"] > 0
            ) and row["nonbinary_count"] > 0:
                expected_class = ExactDuplicateClass.MULTIPLE_CLEAR_WITH_NONBINARY
            elif row["clear_positive_count"] > 0 or row[
                "clear_negative_count"
            ] > 0:
                expected_class = ExactDuplicateClass.MULTIPLE_CLEAR_SAME_LABEL
            else:
                expected_class = ExactDuplicateClass.MULTIPLE_NONBINARY_ONLY
            if row["exact_duplicate_class"] != expected_class.value:
                raise ValueError("exact_duplicate_class 与计数派生结果不一致")


def validate_manifest_maps(
    release_artifacts: Mapping[str, Any], audit_only_artifacts: Mapping[str, Any]
) -> None:
    release_paths = set(release_artifacts)
    audit_paths = set(audit_only_artifacts)
    overlap = release_paths & audit_paths
    if overlap:
        raise ValueError(f"release/audit-only artifact 路径重叠：{sorted(overlap)}")
    for path in release_paths | audit_paths:
        validate_relative_path(path)
        schema = SCHEMA_REGISTRY.get(path)
        if schema is None:
            raise ValueError(f"manifest 引用了未注册 artifact：{path}")
        expected_class = (
            ArtifactClass.RELEASE if path in release_paths else ArtifactClass.AUDIT_ONLY
        )
        if schema.artifact_class is not expected_class:
            raise ValueError(f"artifact class 与 manifest map 不一致：{path}")


def read_and_validate_csv(
    path: Path, schema: ArtifactSchema, *, formal: bool = False
) -> list[dict[str, Any]]:
    """解析 CSV 每一行并校验类型、唯一键、排序和 canonical bytes。"""

    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise ValueError(f"CSV 编码、换行或结尾不符合规范：{path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"CSV 为空：{path}") from None
        validate_columns(header, schema)
        rows: list[dict[str, Any]] = []
        for row_number, values in enumerate(reader, start=2):
            if len(values) != len(schema.fields):
                raise ValueError(f"CSV 第 {row_number} 个逻辑记录列数错误：{path}")
            rows.append(
                {
                    spec.name: parse_csv_scalar(value, spec)
                    for spec, value in zip(schema.fields, values)
                }
            )
    validate_rows(rows, schema, formal=formal)
    if serialize_csv(rows, schema) != raw:
        raise ValueError(f"CSV 行排序或字节序列化不符合 registry：{path}")
    return rows


def read_and_validate_json(path: Path, schema: ArtifactSchema) -> dict[str, Any]:
    """校验 JSON 顶层对象、精确字段、类型和 canonical bytes。"""

    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON artifact 无法解析：{path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact 顶层必须是对象：{path}")
    validate_row(value, schema)
    if "schema_version" in value and value["schema_version"] != schema.schema_version:
        raise ValueError(f"JSON artifact schema_version 不一致：{path}")
    if raw != canonical_json_bytes(value):
        raise ValueError(f"JSON artifact 不是 canonical bytes：{path}")
    return value


def collect_regular_files(root: Path) -> set[str]:
    """收集普通文件并拒绝任一 symlink。"""

    result: set[str] = set()
    for path in root.rglob("*"):
        reject_symlink_chain(root, path)
        if path.is_file():
            result.add(path.relative_to(root).as_posix())
    return result


def validate_artifact_file_set(root: Path, expected: set[str]) -> None:
    for path in expected:
        validate_relative_path(path)
    actual = collect_regular_files(root)
    if actual != expected:
        raise ValueError(
            "artifact 文件集合不一致；"
            f"缺少={sorted(expected - actual)}，多出={sorted(actual - expected)}"
        )
