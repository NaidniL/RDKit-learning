"""从冻结来源事实重建标签规则。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .enums import LabelRule, SourceDataset


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
IRIS_CANDIDATE_NEGATIVE = {"not likely to be carcinogenic to humans"}
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


@dataclass(frozen=True)
class LabelDecision:
    category: str
    candidate: str
    confidence: str
    reason: str
    rule: LabelRule
    normalized_label: int | None


def _cpdb_decision(label_raw: str, payload: Mapping[str, Any]) -> LabelDecision:
    opinion = str(payload.get("opinion", "")).strip().lower()
    inad = str(payload.get("inad", "")).strip().lower()
    if label_raw != str(payload.get("opinion", "")):
        raise ValueError("CPDB label_raw 与 source_payload_json.opinion 不一致")
    if inad == "i":
        return LabelDecision(
            "uncertain", "", "none", "实验证据不足", LabelRule.NONBINARY_UNCERTAIN, None
        )
    if opinion in {"+", "c"}:
        return LabelDecision(
            "positive", "positive", "high", "明确阳性", LabelRule.CPDB_CLEAR_POSITIVE, 1
        )
    if opinion == "-":
        return LabelDecision(
            "negative", "negative", "high", "明确阴性", LabelRule.CPDB_CLEAR_NEGATIVE, 0
        )
    if opinion in {"p", "a"}:
        return LabelDecision(
            "uncertain",
            "positive",
            "medium",
            "提示性阳性证据",
            LabelRule.NONBINARY_UNCERTAIN,
            None,
        )
    if opinion == "e":
        return LabelDecision(
            "uncertain", "", "none", "证据不明确", LabelRule.NONBINARY_UNCERTAIN, None
        )
    return LabelDecision(
        "uncertain", "", "none", "无明确判断", LabelRule.NONBINARY_UNCERTAIN, None
    )


def _iris_decision(label_raw: str) -> LabelDecision:
    normalized = " ".join(label_raw.casefold().split())
    if normalized in IRIS_STRICT_POSITIVE:
        return LabelDecision(
            "positive",
            "positive",
            "high",
            "明确人类致癌物",
            LabelRule.IRIS_HUMAN_POSITIVE,
            1,
        )
    if normalized in IRIS_STRICT_NEGATIVE:
        return LabelDecision(
            "negative",
            "negative",
            "high",
            "明确人类非致癌物",
            LabelRule.IRIS_HUMAN_NEGATIVE,
            0,
        )
    if normalized in IRIS_CANDIDATE_POSITIVE:
        return LabelDecision(
            "uncertain",
            "positive",
            "medium",
            "较弱的阳性证据权重",
            LabelRule.NONBINARY_UNCERTAIN,
            None,
        )
    if normalized in IRIS_CANDIDATE_NEGATIVE:
        return LabelDecision(
            "uncertain",
            "negative",
            "medium",
            "存在暴露途径或剂量条件的阴性候选",
            LabelRule.NONBINARY_UNCERTAIN,
            None,
        )
    return LabelDecision(
        "uncertain",
        "",
        "none",
        "无法二分类或证据权重不足",
        LabelRule.NONBINARY_UNCERTAIN,
        None,
    )


def _ccris_decision(label_raw: str, endpoint: str) -> LabelDecision:
    if endpoint == "noncarcinogenicity_endpoint_only":
        if label_raw != "":
            raise ValueError("非致癌性终点记录的 label_raw 必须为空")
        return LabelDecision(
            "excluded",
            "",
            "none",
            "无致癌性试验记录",
            LabelRule.NONCARCINOGENICITY_ENDPOINT_ONLY,
            None,
        )
    if endpoint != "carcinogenicity":
        raise ValueError(f"CCRIS 未知终点：{endpoint!r}")
    normalized = " ".join(label_raw.upper().split())
    if normalized == "POSITIVE":
        return LabelDecision(
            "positive",
            "positive",
            "high",
            "明确阳性白名单",
            LabelRule.CCRIS_EXACT_POSITIVE,
            1,
        )
    if normalized == "NEGATIVE":
        return LabelDecision(
            "negative",
            "negative",
            "high",
            "明确阴性白名单",
            LabelRule.CCRIS_EXACT_NEGATIVE,
            0,
        )
    candidate = ""
    if normalized.startswith("POSITIVE"):
        candidate = "positive"
    elif normalized.startswith("NEGATIVE"):
        candidate = "negative"
    if any(marker in normalized for marker in CCRIS_UNCERTAINTY_MARKERS):
        confidence = "medium" if candidate else "none"
        reason = "带限制性描述的结果"
    elif candidate:
        confidence = "medium"
        reason = "未纳入严格白名单的带方向结果"
    else:
        confidence = "none"
        reason = "无法映射的结果"
    return LabelDecision(
        "uncertain",
        candidate,
        confidence,
        reason,
        LabelRule.NONBINARY_UNCERTAIN,
        None,
    )


def derive_label(
    source: SourceDataset,
    *,
    label_raw: str,
    endpoint: str,
    payload: Mapping[str, Any],
) -> LabelDecision:
    """使用互斥且穷尽的来源规则重建标签。"""

    if source is SourceDataset.CPDB:
        return _cpdb_decision(label_raw, payload)
    if source is SourceDataset.IRIS:
        return _iris_decision(label_raw)
    if source is SourceDataset.CCRIS:
        return _ccris_decision(label_raw, endpoint)
    raise AssertionError(f"未实现标签规则：{source.value}")
