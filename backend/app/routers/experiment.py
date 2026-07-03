"""
实验控制平面 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional

from app.database import get_db
from app.models import ModelConfig
from app.models.experiment import (
    ExperimentBatch, ExperimentCombination, ExperimentTask,
    BatchStatus, TaskStatus, TaskStage,
)
from app.schemas import (
    ExperimentBatchCreate, ExperimentBatchOut, ExperimentDetailOut,
    ExperimentListResponse, ExperimentCombinationCreate,
    ExperimentCombinationUpdate, ExperimentCombinationOut,
    ExperimentPatientScopeUpdate, ExperimentControlAction,
    ExperimentTaskSummary, ExperimentMetrics,
)
from app.services.experiment_planner import plan_tasks, invalidate_tasks
from app.services.experiment_metrics import get_batch_metrics

router = APIRouter()


@router.get("", response_model=list[ExperimentListResponse])
async def list_experiments(db: AsyncSession = Depends(get_db)):
    """获取实验批次列表"""
    result = await db.execute(
        select(ExperimentBatch).order_by(ExperimentBatch.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ExperimentBatchOut)
async def create_experiment(
    data: ExperimentBatchCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建实验批次"""
    batch = ExperimentBatch(
        name=data.name,
        description=data.description,
        selected_dates=data.selected_dates,
        selected_patient_ids=data.selected_patient_ids,
        status=BatchStatus.PENDING.value,
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return batch


@router.get("/{batch_id}", response_model=ExperimentDetailOut)
async def get_experiment(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取实验详情"""
    result = await db.execute(
        select(ExperimentBatch)
        .options(selectinload(ExperimentBatch.combinations))
        .where(ExperimentBatch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="实验不存在")
    return batch


@router.post("/{batch_id}/combinations", response_model=ExperimentCombinationOut)
async def add_combination(
    batch_id: int,
    data: ExperimentCombinationCreate,
    db: AsyncSession = Depends(get_db),
):
    """添加实验组合"""
    batch = await db.get(ExperimentBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="实验不存在")

    combo = ExperimentCombination(
        batch_id=batch_id,
        asr_model_id=data.asr_model_id,
        llm_model_id=data.llm_model_id,
        prompt_name=data.prompt_name,
        prompt_template=data.prompt_template,
        hotwords=data.hotwords,
    )
    db.add(combo)
    await db.commit()
    await db.refresh(combo)
    return combo


@router.put("/{batch_id}/combinations/{combo_id}", response_model=ExperimentCombinationOut)
async def update_combination(
    batch_id: int,
    combo_id: int,
    data: ExperimentCombinationUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新实验组合"""
    result = await db.execute(
        select(ExperimentCombination).where(
            ExperimentCombination.id == combo_id,
            ExperimentCombination.batch_id == batch_id,
        )
    )
    combo = result.scalar_one_or_none()
    if not combo:
        raise HTTPException(status_code=404, detail="组合不存在")

    # Store old values for invalidation
    old_values = {
        "asr_model_id": combo.asr_model_id,
        "llm_model_id": combo.llm_model_id,
        "prompt_template": combo.prompt_template,
        "hotwords": combo.hotwords,
    }

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(combo, field, value)

    await db.commit()

    # Invalidate affected tasks
    from app.services.experiment_planner import changed_stage
    new_values = {
        "asr_model_id": combo.asr_model_id,
        "llm_model_id": combo.llm_model_id,
        "prompt_template": combo.prompt_template,
        "hotwords": combo.hotwords,
    }
    stage = changed_stage(old_values, new_values)
    if stage:
        await invalidate_tasks(db, combo_id, stage)

    await db.refresh(combo)
    return combo


@router.put("/{batch_id}/patients", response_model=ExperimentBatchOut)
async def update_patient_scope(
    batch_id: int,
    data: ExperimentPatientScopeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新患者范围"""
    batch = await db.get(ExperimentBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="实验不存在")

    batch.selected_patient_ids = data.selected_patient_ids
    await db.commit()
    await db.refresh(batch)
    return batch


@router.post("/{batch_id}/start", response_model=dict)
async def start_experiment(
    batch_id: int,
    data: ExperimentControlAction = ExperimentControlAction(),
    db: AsyncSession = Depends(get_db),
):
    """启动实验"""
    result = await db.execute(
        select(ExperimentBatch)
        .options(selectinload(ExperimentBatch.combinations))
        .where(ExperimentBatch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="实验不存在")

    enabled_combos = [c for c in batch.combinations if c.enabled]
    if not enabled_combos:
        raise HTTPException(status_code=400, detail="没有启用的实验组合")

    if not batch.selected_patient_ids:
        raise HTTPException(status_code=400, detail="没有选择患者")

    # Get patient IDs from database
    from app.models import PatientRecord
    patient_result = await db.execute(
        select(PatientRecord.id).where(
            PatientRecord.record_id.in_(batch.selected_patient_ids)
        )
    )
    patient_ids = [r[0] for r in patient_result.all()]

    if not patient_ids:
        raise HTTPException(status_code=400, detail="所选患者不存在")

    # Generate tasks for each combination
    total_tasks = 0
    for combo in enabled_combos:
        tasks = await plan_tasks(db, batch.id, combo.id, patient_ids)
        total_tasks += len(tasks)

    batch.total_tasks = total_tasks
    batch.status = BatchStatus.RUNNING.value
    await db.commit()

    return {"batch_id": batch_id, "total_tasks": total_tasks, "status": "running"}


@router.post("/{batch_id}/pause", response_model=ExperimentBatchOut)
async def pause_experiment(
    batch_id: int,
    data: ExperimentControlAction = ExperimentControlAction(),
    db: AsyncSession = Depends(get_db),
):
    """暂停实验"""
    batch = await db.get(ExperimentBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="实验不存在")
    if batch.status != BatchStatus.RUNNING.value:
        raise HTTPException(status_code=400, detail="实验未在运行")

    batch.status = BatchStatus.PAUSED.value
    await db.commit()
    await db.refresh(batch)
    return batch


@router.post("/{batch_id}/resume", response_model=ExperimentBatchOut)
async def resume_experiment(
    batch_id: int,
    data: ExperimentControlAction = ExperimentControlAction(),
    db: AsyncSession = Depends(get_db),
):
    """继续实验"""
    batch = await db.get(ExperimentBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="实验不存在")
    if batch.status != BatchStatus.PAUSED.value:
        raise HTTPException(status_code=400, detail="实验未暂停")

    batch.status = BatchStatus.RUNNING.value
    await db.commit()
    await db.refresh(batch)
    return batch


@router.post("/{batch_id}/cancel", response_model=ExperimentBatchOut)
async def cancel_experiment(
    batch_id: int,
    data: ExperimentControlAction = ExperimentControlAction(),
    db: AsyncSession = Depends(get_db),
):
    """取消实验"""
    batch = await db.get(ExperimentBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="实验不存在")

    batch.status = BatchStatus.CANCELLED.value

    # Cancel pending/running tasks
    result = await db.execute(
        select(ExperimentTask).where(
            ExperimentTask.batch_id == batch_id,
            ExperimentTask.status.in_([TaskStatus.PENDING.value, TaskStatus.RUNNING.value]),
        )
    )
    for task in result.scalars().all():
        task.status = TaskStatus.CANCELLED.value

    await db.commit()
    await db.refresh(batch)
    return batch


@router.post("/{batch_id}/retry", response_model=dict)
async def retry_failures(
    batch_id: int,
    data: ExperimentControlAction = ExperimentControlAction(),
    db: AsyncSession = Depends(get_db),
):
    """重试失败任务"""
    result = await db.execute(
        select(ExperimentTask).where(
            ExperimentTask.batch_id == batch_id,
            ExperimentTask.status == TaskStatus.FAILED.value,
        )
    )
    failed_tasks = result.scalars().all()

    for task in failed_tasks:
        task.status = TaskStatus.PENDING.value
        task.retry_count = 0
        task.error_type = None
        task.error_message = None

    await db.commit()
    return {"batch_id": batch_id, "retried": len(failed_tasks)}


@router.get("/{batch_id}/tasks", response_model=list[ExperimentTaskSummary])
async def list_tasks(
    batch_id: int,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """获取实验任务列表"""
    query = select(ExperimentTask).where(ExperimentTask.batch_id == batch_id)
    if status:
        query = query.where(ExperimentTask.status == status)
    result = await db.execute(query.order_by(ExperimentTask.id))
    return result.scalars().all()


@router.get("/{batch_id}/metrics")
async def get_metrics(batch_id: int, db: AsyncSession = Depends(get_db)):
    """获取实验指标"""
    return await get_batch_metrics(db, batch_id)


@router.get("/{batch_id}/results")
async def get_results(batch_id: int, db: AsyncSession = Depends(get_db)):
    """获取实验结果列表"""
    result = await db.execute(
        select(ExperimentTask).where(ExperimentTask.batch_id == batch_id)
    )
    return result.scalars().all()
