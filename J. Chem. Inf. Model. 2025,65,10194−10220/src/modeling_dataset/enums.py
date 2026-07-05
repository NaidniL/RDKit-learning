"""阶段 2 使用的受控枚举。"""

from __future__ import annotations

from enum import Enum
from typing import Type, TypeVar


class ControlledStringEnum(str, Enum):
    """拒绝未知字符串的枚举基类。"""

    @classmethod
    def parse(cls, value: str) -> "ControlledStringEnum":
        try:
            return cls(value)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in cls)
            raise ValueError(
                f"未知的 {cls.__name__} 值：{value!r}；允许值：{allowed}"
            ) from exc


class DatasetRole(ControlledStringEnum):
    DEVELOPMENT = "development"
    EXTERNAL = "external"


class SourceDataset(ControlledStringEnum):
    CPDB = "cpdb"
    IRIS = "iris"
    CCRIS = "ccris"


class LabelStatus(ControlledStringEnum):
    CLEAR_POSITIVE = "clear_positive"
    CLEAR_NEGATIVE = "clear_negative"
    CONFLICT = "conflict"
    UNCERTAIN = "uncertain"


class StructureStatus(ControlledStringEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"


class LeakageStatus(ControlledStringEnum):
    NOT_APPLICABLE = "not_applicable"
    CLEAR = "clear"
    EXACT_OVERLAP = "exact_overlap"
    CONNECTIVITY_OVERLAP = "connectivity_overlap"


class ReviewStatus(ControlledStringEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    CONFIRMED_EXCLUDE = "confirmed_exclude"


class ReviewDecision(ControlledStringEnum):
    CONFIRM_EXCLUDE = "confirm_exclude"


class SplitEligibility(ControlledStringEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE_LABEL = "ineligible_label"
    INELIGIBLE_STRUCTURE = "ineligible_structure"
    INELIGIBLE_LEAKAGE = "ineligible_leakage"


class LabelRule(ControlledStringEnum):
    CPDB_CLEAR_POSITIVE = "cpdb_clear_positive"
    CPDB_CLEAR_NEGATIVE = "cpdb_clear_negative"
    IRIS_HUMAN_POSITIVE = "iris_human_positive"
    IRIS_HUMAN_NEGATIVE = "iris_human_negative"
    CCRIS_EXACT_POSITIVE = "ccris_exact_positive"
    CCRIS_EXACT_NEGATIVE = "ccris_exact_negative"
    NONBINARY_UNCERTAIN = "nonbinary_uncertain"
    NONCARCINOGENICITY_ENDPOINT_ONLY = "noncarcinogenicity_endpoint_only"


class EvidenceType(ControlledStringEnum):
    HUMAN_WEIGHT_OF_EVIDENCE = "human_weight_of_evidence"
    ANIMAL_EXPERIMENTAL = "animal_experimental"
    EXPERIMENTAL_UNSPECIFIED = "experimental_unspecified"


class ExactDuplicateClass(ControlledStringEnum):
    SINGLE_RECORD = "single_record"
    MULTIPLE_CLEAR_SAME_LABEL = "multiple_clear_same_label"
    MULTIPLE_CLEAR_WITH_NONBINARY = "multiple_clear_with_nonbinary"
    MULTIPLE_CLEAR_CONFLICTING = "multiple_clear_conflicting"
    MULTIPLE_NONBINARY_ONLY = "multiple_nonbinary_only"


class RelationType(ControlledStringEnum):
    SAME_CONNECTIVITY = "same_connectivity"
    STEREO_VARIANT = "stereo_variant"
    TAUTOMER_RELATED = "tautomer_related"
    HIGH_SIMILARITY = "high_similarity"


class ComparisonScope(ControlledStringEnum):
    DEVELOPMENT = "development"
    EXTERNAL = "external"
    CROSS_ROLE = "cross_role"


class LabelRelation(ControlledStringEnum):
    SAME = "same"
    OPPOSITE = "opposite"
    NOT_COMPARABLE = "not_comparable"


class ResolutionRule(ControlledStringEnum):
    UNANIMOUS_CLEAR_POSITIVE = "unanimous_clear_positive"
    UNANIMOUS_CLEAR_NEGATIVE = "unanimous_clear_negative"
    CONFIRMED_EXACT_LABEL_CONFLICT_EXCLUDE = (
        "confirmed_exact_label_conflict_exclude"
    )
    NO_CLEAR_BINARY_LABEL = "no_clear_binary_label"
    STRUCTURE_INELIGIBLE = "structure_ineligible"
    EXTERNAL_EXACT_LEAKAGE = "external_exact_leakage"
    EXTERNAL_CONNECTIVITY_LEAKAGE = "external_connectivity_leakage"
    EXTERNAL_TAUTOMER_OVERLAP_REPORTED = "external_tautomer_overlap_reported"


class QuerySplit(ControlledStringEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    EXTERNAL_TEST = "external_test"
    EXTERNAL_TAUTOMER_SENSITIVITY = "external_tautomer_sensitivity"


class SummaryStatus(ControlledStringEnum):
    OK = "ok"
    NO_OBSERVATIONS = "no_observations"


class SmdStatus(ControlledStringEnum):
    OK = "ok"
    UNDEFINED_ZERO_VARIANCE = "undefined_zero_variance"
    INSUFFICIENT_OBSERVATIONS = "insufficient_observations"


class TestStatus(ControlledStringEnum):
    OK = "ok"
    INSUFFICIENT_OBSERVATIONS = "insufficient_observations"
    DEGENERATE_TABLE = "degenerate_table"


class ScaffoldSummaryStatus(ControlledStringEnum):
    OK = "ok"
    NO_SCAFFOLDS = "no_scaffolds"


class LeakageContributionType(ControlledStringEnum):
    COMPOUND_ROLE = "compound_role"
    EXCLUDED_RECORD_COMPONENT = "excluded_record_component"


EnumType = TypeVar("EnumType", bound=ControlledStringEnum)


ENUM_TYPES: dict[str, Type[ControlledStringEnum]] = {
    enum_type.__name__: enum_type
    for enum_type in (
        DatasetRole,
        SourceDataset,
        LabelStatus,
        StructureStatus,
        LeakageStatus,
        ReviewStatus,
        ReviewDecision,
        SplitEligibility,
        LabelRule,
        EvidenceType,
        ExactDuplicateClass,
        RelationType,
        ComparisonScope,
        LabelRelation,
        ResolutionRule,
        QuerySplit,
        SummaryStatus,
        SmdStatus,
        TestStatus,
        ScaffoldSummaryStatus,
        LeakageContributionType,
    )
}


ENUM_RANKS: dict[str, dict[str, int]] = {
    "dataset_role": {
        DatasetRole.DEVELOPMENT.value: 0,
        DatasetRole.EXTERNAL.value: 1,
    },
    "query_split": {
        QuerySplit.TRAIN.value: 0,
        QuerySplit.VALIDATION.value: 1,
        QuerySplit.EXTERNAL_TEST.value: 2,
        QuerySplit.EXTERNAL_TAUTOMER_SENSITIVITY.value: 3,
    },
}


def parse_enum(enum_type: Type[EnumType], value: str) -> EnumType:
    """将字符串转换为指定枚举，未知值立即报错。"""

    return enum_type.parse(value)  # type: ignore[return-value]
