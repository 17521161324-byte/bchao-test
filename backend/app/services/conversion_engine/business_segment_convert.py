"""Business-segment driven conversion.

This layer converts only spans that the business segment locator has already
classified. It keeps the ASR conversion close to the B-ultrasound domain:
medical terms and medical data can be normalized, locators/noise are kept as
anchors only.
"""
from __future__ import annotations

from typing import Any

from app.services.conversion_engine.business_segment_locator import locate_business_segments


def apply_business_segment_conversion(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Convert located business segments and return conversion details.

    Rules:
    - medical_term participates in conversion, e.g. 面膜 -> 内膜.
    - medical_data participates in conversion, e.g. 十一点一 -> 11.1,
      五八乘以三八 -> 58×38, 五回声 -> 无回声.
    - locator/noise do not mutate text.
    - “无回声” is a global remark, not part of ovary size.
    """
    if not text:
        return text, []

    conversions: list[dict[str, Any]] = []
    replacements: list[dict[str, Any]] = []
    for segment in locate_business_segments(text):
        if segment.get("segment_type") not in ("medical_term", "medical_data"):
            continue
        raw = str(segment.get("text") or "")
        converted = _format_normalized(segment.get("normalized"))
        if not raw or not converted or raw == converted:
            continue
        if segment.get("segment_type") == "medical_term" and raw.endswith("卵巢大小"):
            # “左/右卵巢大小”本身已经是正确业务表达；locator 中的 normalized
            # 是字段归一名，不应把“大小”删掉。
            continue
        conversion = {
            "rule_id": _rule_id_for(segment),
            "raw": raw,
            "converted": converted,
            "action": "AUTO",
            "category": str(segment.get("segment_type") or "business_segment"),
            "field_code": str(segment.get("field_code") or ""),
            "start": int(segment.get("start") or 0),
            "end": int(segment.get("end") or 0),
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
