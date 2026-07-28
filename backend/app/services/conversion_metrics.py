"""ASR 转化评估指标计算。"""

from collections import defaultdict
from typing import Any

from app.models import AsrConversionDetail, AsrConversionRecord


ACTUAL_CONVERSION_ACTIONS = {"replace", "insert", "delete", "format", "candidate", "review"}
HIGH_RISK_JUDGEMENTS = {"wrong", "over_converted"}


def final_judgement(detail: AsrConversionDetail) -> str:
    return detail.manual_judgement or detail.final_judgement or detail.system_judgement or "pending"


def is_actual_conversion(detail: AsrConversionDetail) -> bool:
    if detail.action_type in ACTUAL_CONVERSION_ACTIONS and detail.action_type != "no_change":
        return (detail.raw_fragment or "") != (detail.converted_fragment or "")
    return False


def is_high_risk_error(detail: AsrConversionDetail) -> bool:
    risk = (detail.risk_level == "high") or bool(detail.risk_type)
    return risk and final_judgement(detail) in HIGH_RISK_JUDGEMENTS


def calculate_conversion_metrics(record: AsrConversionRecord) -> dict[str, Any]:
    details = list(record.details or [])
    actual = [d for d in details if is_actual_conversion(d)]
    candidates = [d for d in details if d.action_type == "candidate"]
    correct = [d for d in actual if final_judgement(d) == "correct"]
    wrong = [d for d in actual if final_judgement(d) == "wrong"]
    over = [d for d in actual if final_judgement(d) == "over_converted"]
    missed = [d for d in details if final_judgement(d) == "missed"]
    candidate_hits = [d for d in candidates if final_judgement(d) == "correct"]
    high_risk_errors = [d for d in details if is_high_risk_error(d)]

    category_stats: dict[str, dict[str, int | float]] = defaultdict(lambda: {
        "actual_conversion_count": 0,
        "correct_conversion_count": 0,
        "wrong_conversion_count": 0,
        "missed_conversion_count": 0,
        "over_conversion_count": 0,
        "high_risk_error_count": 0,
        "conversion_accuracy": 0.0,
    })
    for detail in details:
        category = detail.category or "other"
        stat = category_stats[category]
        if is_actual_conversion(detail):
            stat["actual_conversion_count"] += 1
        judgement = final_judgement(detail)
        if judgement == "correct" and is_actual_conversion(detail):
            stat["correct_conversion_count"] += 1
        elif judgement == "wrong" and is_actual_conversion(detail):
            stat["wrong_conversion_count"] += 1
        elif judgement == "missed":
            stat["missed_conversion_count"] += 1
        elif judgement == "over_converted" and is_actual_conversion(detail):
            stat["over_conversion_count"] += 1
        if is_high_risk_error(detail):
            stat["high_risk_error_count"] += 1

    for stat in category_stats.values():
        denominator = int(stat["actual_conversion_count"] or 0)
        stat["conversion_accuracy"] = (int(stat["correct_conversion_count"]) / denominator) if denominator else 0.0

    actual_count = len(actual)
    return {
        "record_id": record.id,
        "actual_conversion_count": actual_count,
        "correct_conversion_count": len(correct),
        "wrong_conversion_count": len(wrong),
        "missed_conversion_count": len(missed),
        "over_conversion_count": len(over),
        "candidate_count": len(candidates),
        "high_risk_error_count": len(high_risk_errors),
        "conversion_accuracy": len(correct) / actual_count if actual_count else 0.0,
        "error_rate": len(wrong) / actual_count if actual_count else 0.0,
        "missed_rate": len(missed) / len(details) if details else 0.0,
        "over_conversion_rate": len(over) / actual_count if actual_count else 0.0,
        "candidate_hit_rate": len(candidate_hits) / len(candidates) if candidates else 0.0,
        "category_stats": dict(category_stats),
    }
