"""ASR 转化片段自动初判。"""

from app.models import AsrConversionDetail, AsrConversionRecord


HIGH_RISK_CATEGORIES = {"number_format", "left_right", "negation", "clinical_decision"}
HIGH_RISK_TYPES = {"number_error", "left_right", "negation", "clinical_decision"}


def judge_detail(record: AsrConversionRecord, detail: AsrConversionDetail) -> str:
    """给单个片段生成系统初判。

    P0 是启发式初判，最终统计可由人工 judgement 覆盖。
    """
    raw = (detail.raw_fragment or "").strip()
    converted = (detail.converted_fragment or "").strip()
    reference = record.reference_text or ""
    converted_text = record.converted_text or ""

    if not raw and not converted:
        return "unchanged"
    if raw == converted:
        if raw and raw in reference:
            return "unchanged"
        return "missed"
    if converted and converted in reference:
        return "correct"
    if raw and raw in reference and (converted not in reference):
        if detail.category == "number_format" or detail.risk_type == "number_error":
            return "wrong"
        return "over_converted"
    if converted and converted not in converted_text:
        return "wrong"
    return "wrong"


def apply_auto_judge(record: AsrConversionRecord) -> list[AsrConversionDetail]:
    """更新记录下所有 detail 的 system/final judgement。"""
    for detail in record.details:
        judgement = judge_detail(record, detail)
        detail.system_judgement = judgement
        detail.final_judgement = detail.manual_judgement or judgement
        if detail.category in HIGH_RISK_CATEGORIES or detail.risk_type in HIGH_RISK_TYPES:
            detail.risk_level = detail.risk_level or "high"
            if detail.risk_level == "low":
                detail.risk_level = "high"
    return list(record.details)
