"""
实验任务规划与失效规则
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.experiment import ExperimentTask, ExperimentCombination, TaskStatus, TaskStage


def changed_stage(before: dict, after: dict) -> Optional[str]:
    """
    判断配置变化影响的阶段。

    Returns:
        "asr" - ASR 模型或热词变化，需要重跑 ASR+LLM+评估
        "llm" - LLM 模型或提示词变化，只需重跑 LLM+评估
        None  - 无影响执行的变化
    """
    # Normalize hotwords for comparison (order-independent)
    before_hotwords = sorted(before.get("hotwords", []))
    after_hotwords = sorted(after.get("hotwords", []))

    # ASR-related changes
    if before.get("asr_model_id") != after.get("asr_model_id"):
        return "asr"
    if before_hotwords != after_hotwords:
        return "asr"

    # LLM-related changes
    if before.get("llm_model_id") != after.get("llm_model_id"):
        return "llm"
    if before.get("prompt_template") != after.get("prompt_template"):
        return "llm"

    return None


def task_pairs(patient_ids: list[int], combination_ids: list[int]) -> list[tuple[int, int]]:
    """
    生成患者 × 组合的笛卡尔积任务对。
    顺序：患者优先（patient-major）。
    """
    return [(pid, cid) for pid in patient_ids for cid in combination_ids]


async def plan_tasks(
    db: AsyncSession,
    batch_id: int,
    combination_id: int,
    patient_ids: list[int],
) -> list[ExperimentTask]:
    """
    Idempotent upsert: create missing tasks for the given patients × combination.
    Returns all tasks for this combination.
    """
    # Get existing tasks for this combination
    result = await db.execute(
        select(ExperimentTask).where(
            ExperimentTask.combination_id == combination_id,
            ExperimentTask.patient_id.in_(patient_ids),
        )
    )
    existing = {t.patient_id: t for t in result.scalars().all()}

    # Create missing tasks
    for pid in patient_ids:
        if pid not in existing:
            task = ExperimentTask(
                batch_id=batch_id,
                combination_id=combination_id,
                patient_id=pid,
                stage=TaskStage.ASR.value,
                status=TaskStatus.PENDING.value,
            )
            db.add(task)

    await db.commit()

    # Return all tasks
    result = await db.execute(
        select(ExperimentTask).where(
            ExperimentTask.combination_id == combination_id,
            ExperimentTask.patient_id.in_(patient_ids),
        )
    )
    return result.scalars().all()


async def invalidate_tasks(
    db: AsyncSession,
    combination_id: int,
    stage: str,
) -> int:
    """
    Invalidate tasks based on stage change.

    Args:
        stage: "asr" or "llm"

    Returns:
        Number of tasks affected
    """
    result = await db.execute(
        select(ExperimentTask).where(
            ExperimentTask.combination_id == combination_id,
        )
    )
    tasks = result.scalars().all()

    for task in tasks:
        if stage == "asr":
            # Clear ASR + LLM + evaluation, reset to pending
            task.asr_results = []
            task.full_transcript = ""
            task.asr_duration = 0.0
            task.llm_raw_output = None
            task.structured_result = None
            task.summary_text = None
            task.llm_duration = 0.0
            task.evaluation = None
            task.accuracy = None
            task.total_duration = 0.0
            task.error_type = None
            task.error_message = None
            task.stage = TaskStage.ASR.value
            task.status = TaskStatus.PENDING.value
            task.started_at = None
            task.completed_at = None
        elif stage == "llm":
            # Keep ASR transcript, clear LLM + evaluation, reset to pending
            task.llm_raw_output = None
            task.structured_result = None
            task.summary_text = None
            task.llm_duration = 0.0
            task.evaluation = None
            task.accuracy = None
            task.total_duration = 0.0
            task.error_type = None
            task.error_message = None
            task.stage = TaskStage.LLM.value
            task.status = TaskStatus.PENDING.value
            task.started_at = None
            task.completed_at = None

    await db.commit()
    return len(tasks)
