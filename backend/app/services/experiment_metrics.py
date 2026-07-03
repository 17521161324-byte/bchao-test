"""
实验指标聚合服务
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experiment import ExperimentTask, BatchStatus


def calculate_metrics(tasks: list[ExperimentTask]) -> dict:
    """
    计算实验指标的独立聚合。

    Returns dict with separate metrics, no score/rank/best_combination.
    """
    total = len(tasks)
    if total == 0:
        return {
            "total_tasks": 0,
            "success_count": 0,
            "failure_count": 0,
            "asr_success_rate": 0.0,
            "asr_empty_rate": 0.0,
            "avg_asr_duration": 0.0,
            "follicle_accuracy": 0.0,
            "endometrium_accuracy": 0.0,
            "ovary_accuracy": 0.0,
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
    llm_tasks = [t for t in success if t.structured_result is not None]
    llm_fail = [t for t in failed if t.error_type in ["model_timeout", "quota", "unknown"]]

    # Evaluation metrics
    eval_tasks = [t for t in success if t.evaluation]
    field_correct = sum(
        1 for t in eval_tasks
        if t.evaluation.get("accuracy", 0) >= 0.8
    )
    completely_correct = sum(
        1 for t in eval_tasks
        if t.accuracy == 1.0
    )

    return {
        "total_tasks": total,
        "success_count": len(success),
        "failure_count": len(failed),
        "asr_success_rate": len(asr_success) / total,
        "asr_empty_rate": len(asr_empty) / max(len(success), 1),
        "avg_asr_duration": sum(asr_durations) / max(len(asr_durations), 1),
        "follicle_accuracy": field_correct / max(len(eval_tasks), 1),
        "endometrium_accuracy": field_correct / max(len(eval_tasks), 1),
        "ovary_accuracy": field_correct / max(len(eval_tasks), 1),
        "complete_patient_rate": completely_correct / max(len(eval_tasks), 1),
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
