"""
实验控制平面 API 路由
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional

from app.database import get_db
from app.models import ModelConfig, DateFolder, PatientRecord
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
from app.services.experiment_metrics import calculate_metrics
from app.services.experiment_metrics import get_batch_metrics

router = APIRouter()


@router.get("")
async def list_experiments(db: AsyncSession = Depends(get_db)):
    """获取实验批次列表"""
    result = await db.execute(
        select(ExperimentBatch).order_by(ExperimentBatch.created_at.desc())
    )
    batches = result.scalars().all()

    # 手动构建响应数据，避免 schema 验证问题
    output = []
    for b in batches:
        # 确保 selected_patient_ids 是列表
        pids = b.selected_patient_ids
        if pids is None:
            pids = []
        elif isinstance(pids, str):
            try:
                pids = json.loads(pids)
            except:
                pids = []
        else:
            try:
                # 通过 JSON 序列化/反序列化确保是普通列表
                pids = json.loads(json.dumps(pids))
            except:
                pids = []

        dates = b.selected_dates
        if dates is None:
            dates = []
        elif isinstance(dates, str):
            try:
                dates = json.loads(dates)
            except:
                dates = []
        else:
            try:
                dates = json.loads(json.dumps(dates))
            except:
                dates = []

        output.append({
            "id": b.id,
            "name": b.name,
            "status": b.status,
            "remark": b.remark or "",
            "selected_dates": dates,
            "selected_patient_ids": pids,
            "total_tasks": b.total_tasks or 0,
            "success_count": b.success_count or 0,
            "failure_count": b.failure_count or 0,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
            "patient_count": len(pids) if isinstance(pids, list) else 0,
            "field_accuracy": {},
            "asr_models": [],
            "llm_models": [],
            "prompt_templates": [],
        })
    return output


@router.post("", response_model=ExperimentBatchOut)
async def create_experiment(
    data: ExperimentBatchCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建实验批次"""
    batch = ExperimentBatch(
        name=data.name,
        description=data.description,
        remark=data.remark,
        selected_dates=data.selected_dates,
        selected_patient_ids=data.selected_patient_ids,
        status=BatchStatus.PENDING.value,
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return batch


@router.delete("/{batch_id}")
async def delete_experiment(batch_id: int, db: AsyncSession = Depends(get_db)):
    """删除实验批次"""
    batch = await db.get(ExperimentBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="实验不存在")
    await db.delete(batch)
    await db.commit()
    return {"message": "已删除", "id": batch_id}


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
    # 手动构建响应以确保 JSON 字段正确序列化
    return {
        "id": batch.id,
        "name": batch.name,
        "description": batch.description,
        "remark": batch.remark or "",
        "selected_dates": batch.selected_dates or [],
        "selected_patient_ids": batch.selected_patient_ids or [],
        "status": batch.status,
        "total_tasks": batch.total_tasks,
        "success_count": batch.success_count,
        "failure_count": batch.failure_count,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
        "started_at": batch.started_at,
        "completed_at": batch.completed_at,
        "combinations": [
            {
                "id": c.id,
                "batch_id": c.batch_id,
                "asr_model_id": c.asr_model_id,
                "llm_model_id": c.llm_model_id,
                "prompt_name": c.prompt_name or "",
                "prompt_template": c.prompt_template or "",
                "hotwords": c.hotwords or [],
                "enabled": c.enabled,
                "created_at": c.created_at,
            }
            for c in batch.combinations
        ],
    }


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


@router.delete("/{batch_id}/combinations/{combo_id}")
async def delete_combination(
    batch_id: int,
    combo_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除实验组合"""
    from sqlalchemy import delete as sa_delete
    result = await db.execute(
        select(ExperimentCombination).where(
            ExperimentCombination.id == combo_id,
            ExperimentCombination.batch_id == batch_id,
        )
    )
    combo = result.scalar_one_or_none()
    if not combo:
        raise HTTPException(status_code=404, detail="组合不存在")

    # Delete associated tasks
    await db.execute(
        sa_delete(ExperimentTask).where(ExperimentTask.combination_id == combo_id)
    )
    # Delete combination
    await db.delete(combo)
    await db.commit()
    return {"message": "已删除", "id": combo_id}


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
        .where(ExperimentBatch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="实验不存在")

    enabled_combos = await db.execute(
        select(ExperimentCombination).where(
            ExperimentCombination.batch_id == batch_id,
            ExperimentCombination.enabled == True,
        )
    )
    combos = enabled_combos.scalars().all()
    if not combos:
        raise HTTPException(status_code=400, detail="没有启用的实验组合")

    # Only include patients from selected_dates
    patient_records = await db.execute(
        select(PatientRecord)
        .join(DateFolder)
        .where(
            DateFolder.date.in_(batch.selected_dates),
            PatientRecord.record_id.in_(batch.selected_patient_ids),
        )
    )
    patients = patient_records.scalars().all()
    if not patients:
        raise HTTPException(status_code=400, detail="所选日期/患者组合无匹配数据")

    patient_ids = [p.id for p in patients]

    # Generate tasks
    from app.services.experiment_planner import plan_tasks
    total_tasks = 0
    for combo in combos:
        tasks = await plan_tasks(db, batch.id, combo.id, patient_ids)
        total_tasks += len(tasks)

    batch.total_tasks = total_tasks
    batch.status = BatchStatus.RUNNING.value
    await db.commit()

    return {"batch_id": batch_id, "total_tasks": total_tasks, "status": "running"}


@router.get("/{batch_id}/progress")
async def get_progress(batch_id: int, db: AsyncSession = Depends(get_db)):
    """获取实验实时进度"""
    from sqlalchemy import func
    batch = await db.get(ExperimentBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="实验不存在")

    # Count by status
    result = await db.execute(
        select(ExperimentTask.status, func.count(ExperimentTask.id))
        .where(ExperimentTask.batch_id == batch_id)
        .group_by(ExperimentTask.status)
    )
    counts = {row[0]: row[1] for row in result.all()}

    total = batch.total_tasks or 1
    success = counts.get("success", 0)
    failed = counts.get("failed", 0)
    running = counts.get("running", 0)
    pending = counts.get("pending", 0)

    return {
        "batch_id": batch_id,
        "total": total,
        "success": success,
        "failed": failed,
        "running": running,
        "pending": pending,
        "percent": round((success + failed) / total * 100, 1) if total > 0 else 0,
        "status": batch.status,
    }


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


@router.get("/{batch_id}/tasks")
async def list_tasks(
    batch_id: int,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """获取实验任务列表（含患者信息）"""
    query = (
        select(ExperimentTask)
        .options(
            selectinload(ExperimentTask.patient).selectinload(PatientRecord.date_folder),
            selectinload(ExperimentTask.combination).selectinload(ExperimentCombination.asr_model),
            selectinload(ExperimentTask.combination).selectinload(ExperimentCombination.llm_model),
        )
        .where(ExperimentTask.batch_id == batch_id)
    )
    if status:
        query = query.where(ExperimentTask.status == status)
    result = await db.execute(query.order_by(ExperimentTask.id))
    tasks = result.scalars().all()

    output = []
    for t in tasks:
        output.append({
            "id": t.id,
            "batch_id": t.batch_id,
            "combination_id": t.combination_id,
            "patient_id": t.patient_id,
            "record_id": t.patient.record_id if t.patient else None,
            "date": t.patient.date_folder.date if t.patient and t.patient.date_folder else None,
            "stage": t.stage,
            "status": t.status,
            "retry_count": t.retry_count,
            "accuracy": t.accuracy,
            "total_duration": t.total_duration,
            "error_type": t.error_type,
            "created_at": t.created_at,
            "asr_results": t.asr_results,
            "full_transcript": t.full_transcript,
            "structured_result": t.structured_result,
            "evaluation": t.evaluation,
            "combination_asr_name": t.combination.asr_model.name if t.combination and t.combination.asr_model else "",
            "combination_llm_name": t.combination.llm_model.name if t.combination and t.combination.llm_model else "",
            "combination_prompt_name": t.combination.prompt_name or "",
        })
    return output


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
