"""
实验指标聚合服务
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experiment import ExperimentTask, BatchStatus


def calculate_metrics(tasks: list[ExperimentTask]) -> dict:
    """
    计算实验指标的独立聚合，包含各字段准确率。
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
                "endometrium_thickness": 0.0,
                "endometrium_type": 0.0,
                "ovary_size": 0.0,
                "follicle": 0.0,
                "remark": 0.0,
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
    asr_durations = [t.asr_duration for t in success if t.asr_duration > 0]

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

    # 卵巢尺寸（取左右卵巢长/宽四个字段的平均匹配率）
    def ovary_match_rate() -> float:
        if not eval_tasks:
            return 0.0
        fields = ["right_ovary_length", "right_ovary_width", "left_ovary_length", "left_ovary_width"]
        total_match = 0
        total_count = 0
        for t in eval_tasks:
            for f in fields:
                if t.evaluation["fields"].get(f, {}).get("match") is not None:
                    total_count += 1
                    if t.evaluation["fields"][f]["match"]:
                        total_match += 1
        return round(total_match / max(total_count, 1), 4)

    # 卵泡结果（取左右卵泡总数的平均匹配率）
    def follicle_match_rate() -> float:
        if not eval_tasks:
            return 0.0
        fields = ["right_follicle_total", "left_follicle_total"]
        total_match = 0
        total_count = 0
        for t in eval_tasks:
            for f in fields:
                if t.evaluation["fields"].get(f, {}).get("match") is not None:
                    total_count += 1
                    if t.evaluation["fields"][f]["match"]:
                        total_match += 1
        return round(total_match / max(total_count, 1), 4)

    return {
        "total_tasks": total,
        "success_count": len(success),
        "failure_count": len(failed),
        "patient_count": len(patient_ids),
        "asr_success_rate": len(asr_success) / total,
        "asr_empty_rate": len(asr_empty) / max(len(success), 1),
        "avg_asr_duration": sum(asr_durations) / max(len(asr_durations), 1),
        "field_accuracy": {
            "endometrium_thickness": field_match_rate("endometrium_thickness"),
            "endometrium_type": field_match_rate("endometrium_type"),
            "ovary_size": ovary_match_rate(),
            "follicle": follicle_match_rate(),
            "remark": field_match_rate("remark"),
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
