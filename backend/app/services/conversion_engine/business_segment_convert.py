"""Business-segment driven conversion.

This layer converts only spans that the business segment locator has already
classified. It keeps the ASR conversion close to the B-ultrasound domain:
medical terms and medical data can be normalized, locators/noise are kept as
anchors only.
"""
from __future__ import annotations

from typing import Any

from app.services.conversion_engine.business_segment_locator import locate_business_segments
from app.services.conversion_pipeline.decision_registry import DecisionRegistry
from app.services.conversion_pipeline.types import RuleDecision, StepCode


def apply_business_segment_conversion(
    text: str,
    *,
    decision_registry: DecisionRegistry | None = None,
    rule_version: str = "V1.0",
) -> tuple[str, list[dict[str, Any]]]:
    """Convert located business segments and return conversion details.

    Rules:
    - medical_term participates in conversion, e.g. 面膜 -> 内膜.
    - medical_data participates in conversion, e.g. 十一点一 -> 11.1,
      五八乘以三八 -> 58×38. “五回声 → 无回声”由医学词规则决定，本层不再自动归一。
    - locator/noise do not mutate text.
    - “无回声” is a global remark, not part of ovary size.
    - 每个替换生成 RuleDecision 并经决策注册表拦截，防止覆盖医学词层的高风险决策。
    """
    if not text:
        return text, []

    conversions: list[dict[str, Any]] = []
    replacements: list[dict[str, Any]] = []
    for segment in locate_business_segments(text):
        if segment.get("segment_type") not in ("medical_term", "medical_data"):
            continue
        # P0-02：REVIEW 语义的片段（如 S012 缺“型”后缀的 A/B/C 候选）只作候选展示，
        # 不得被本步骤 AUTO 改写正文（如 “14.8A” → “14.8A型”）。
        if str(segment.get("action") or "") == "REVIEW":
            continue
        raw = str(segment.get("text") or "")
        converted = _format_normalized(segment.get("normalized"))
        if not raw or not converted or raw == converted:
            continue
        if segment.get("segment_type") == "medical_term" and raw.endswith("卵巢大小"):
            # “左/右卵巢大小”本身已经是正确业务表达；locator 中的 normalized
            # 是字段归一名，不应把“大小”删掉。
            continue
        start = int(segment.get("start") or 0)
        end = int(segment.get("end") or 0)

        # 决策注册表拦截：若医学词层已有 REVIEW/BLOCK 覆盖同一区间，此处 AUTO 不再执行
        if decision_registry is not None:
            decision = RuleDecision(
                rule_id=_rule_id_for(segment),
                rule_version=rule_version,
                step_code=StepCode.BUSINESS_SEGMENT.value,
                action="AUTO",
                category=str(segment.get("segment_type") or "business_segment"),
                raw=raw,
                converted=converted,
                start=start,
                end=end,
                risk_level="low",
            )
            if not decision_registry.register(decision):
                continue

        conversion = {
            "rule_id": _rule_id_for(segment),
            "raw": raw,
            "converted": converted,
            "action": "AUTO",
            "category": str(segment.get("segment_type") or "business_segment"),
            "field_code": str(segment.get("field_code") or ""),
            "start": start,
            "end": end,
            "confidence": 0.98,
            "risk_level": "low",
            "notes": segment.get("note") or "业务片段定位驱动转化",
        }
        conversions.append(conversion)
        replacements.append(conversion)

    converted_text = _apply_replacements(text, replacements)
    return converted_text, conversions


def _format_normalized(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _rule_id_for(segment: dict[str, Any]) -> str:
    field_code = str(segment.get("field_code") or "unknown")
    if segment.get("segment_type") == "medical_term":
        return f"BS_MEDICAL_TERM_{field_code}".upper()
    return f"BS_MEDICAL_DATA_{field_code}".upper()


def _apply_replacements(text: str, replacements: list[dict[str, Any]]) -> str:
    result = text
    occupied: list[tuple[int, int]] = []
    for item in sorted(replacements, key=lambda row: (int(row["start"]), -(int(row["end"]) - int(row["start"])))):
        start = int(item["start"])
        end = int(item["end"])
        if any(start < old_end and end > old_start for old_start, old_end in occupied):
            continue
        occupied.append((start, end))

    selected = [
        item for item in replacements
        if (int(item["start"]), int(item["end"])) in occupied
    ]
    for item in sorted(selected, key=lambda row: int(row["start"]), reverse=True):
        start = int(item["start"])
        end = int(item["end"])
        result = result[:start] + str(item["converted"]) + result[end:]
    return result
