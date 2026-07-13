"""
实验指标聚合服务
"""
import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experiment import ExperimentTask, BatchStatus

logger = logging.getLogger(__name__)


def calculate_metrics(tasks: list[ExperimentTask]) -> dict:
    """
    计算实验指标的独立聚合，包含各字段准确率。
    新设计：一个实验只有一个组合，指标直接聚合所有任务。
    """
    total = len(tasks)
    if total == 0:
        return {
            "total_tasks": 0,
            "success_count": 0,
            "failure_count": 0,
            "patient_count": 0,
            "asr_success_rate": 0.0,
            "asr_empty_rate": 0.0,
            "avg_asr_duration": 0.0,
            "field_accuracy": {
                "right_follicle": 0.0,
                "left_follicle": 0.0,
                "endometrium_thickness": 0.0,
                "endometrium_type": 0.0,
                "right_ovary": 0.0,
                "left_ovary": 0.0,
            },
            "complete_patient_rate": 0.0,
            "llm_failure_rate": 0.0,
            "total_cost": 0.0,
        }

    success = [t for t in tasks if t.status == "success"]
    failed = [t for t in tasks if t.status == "failed"]

    # ASR metrics
    asr_success = [t for t in success if t.asr_results]
    asr_empty = [t for t in success if not t.asr_results]
    asr_durations = [t.asr_duration for t in success if t.asr_duration and t.asr_duration > 0]

    # LLM metrics
    llm_fail = [t for t in failed if t.error_type in ["model_timeout", "quota", "unknown"]]

    # Per-field accuracy
    eval_tasks = [t for t in success if t.evaluation and t.evaluation.get("fields")]
    patient_ids = set(t.patient_id for t in tasks)

    def field_match_rate(field_key: str) -> float:
        if not eval_tasks:
            return 0.0
        matches = sum(
            1 for t in eval_tasks
            if t.evaluation["fields"].get(field_key, {}).get("match")
        )
        return round(matches / len(eval_tasks), 4)

    # 卵巢尺寸（左/右分别计算：length 和 width 都匹配才算该侧匹配）
    def ovary_side_match_rate(side: str) -> float:
        if not eval_tasks:
            return 0.0
        len_field = f"{side}_ovary_length"
        wid_field = f"{side}_ovary_width"
        total = 0
        matched = 0
        for t in eval_tasks:
            f_len = t.evaluation["fields"].get(len_field, {})
            f_wid = t.evaluation["fields"].get(wid_field, {})
            if f_len.get("identified") is None and f_len.get("truth") is None and wid_field not in t.evaluation["fields"]:
                continue
            total += 1
            if f_len.get("match") and f_wid.get("match"):
                matched += 1
        return round(matched / max(total, 1), 4)

    return {
        "total_tasks": total,
        "success_count": len(success),
        "failure_count": len(failed),
        "patient_count": len(patient_ids),
        "asr_success_rate": len(asr_success) / total,
        "asr_empty_rate": len(asr_empty) / max(len(success), 1),
        "avg_asr_duration": sum(asr_durations) / max(len(asr_durations), 1),
        "field_accuracy": {
            "right_follicle": field_match_rate("right_follicle_total"),
            "left_follicle": field_match_rate("left_follicle_total"),
            "endometrium_thickness": field_match_rate("endometrium_thickness"),
            "endometrium_type": field_match_rate("endometrium_type"),
            "right_ovary": ovary_side_match_rate("right"),
            "left_ovary": ovary_side_match_rate("left"),
        },
        "complete_patient_rate": sum(1 for t in eval_tasks if t.accuracy == 1.0) / max(len(eval_tasks), 1),
        "llm_failure_rate": len(llm_fail) / max(len(success), 1),
        "total_cost": sum(t.cost or 0 for t in tasks),
    }


async def get_batch_metrics(db: AsyncSession, batch_id: int) -> dict:
    """Get aggregated metrics for a batch"""
    result = await db.execute(
        select(ExperimentTask).where(ExperimentTask.batch_id == batch_id)
    )
    tasks = result.scalars().all()
    return calculate_metrics(tasks)
