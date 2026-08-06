"""流水线调试 API（Task 15）。

前缀 /api/conversion-pipeline：
- POST /executions（创建执行，run_mode=create_only|run_all）
- GET  /executions/{id}
- POST /executions/{id}/run-step（单步，只能执行下一步，用冻结 config_snapshot）
- POST /executions/{id}/fork-from-step（新规则版本重跑，不覆盖旧历史）
- GET  /compare?left_execution_id=&right_execution_id=
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    ConversionConfigVersion,
    ConversionPipelineExecution,
    ConversionPipelineStep,
    TextValidationRun,
)
from app.schemas.conversion_pipeline import (
    PipelineExecutionCreate,
    PipelineExecutionOut,
    PipelineRunFromStepRequest,
    PipelineRunStepRequest,
)
from app.services.conversion_config import (
    load_enabled_lexicon_rules,
    load_enabled_runtime_rules,
)
from app.services.conversion_pipeline.orchestrator import build_config_hash, run_pipeline

router = APIRouter()

STEP_COUNT = 7


async def _load_steps(db: AsyncSession, execution_id: int) -> list[ConversionPipelineStep]:
    rows = (
        await db.execute(
            select(ConversionPipelineStep)
            .where(ConversionPipelineStep.execution_id == execution_id)
            .order_by(ConversionPipelineStep.step_order.asc(), ConversionPipelineStep.id.asc())
        )
    ).scalars().all()
    return list(rows)


async def _execution_out(db: AsyncSession, execution: ConversionPipelineExecution) -> PipelineExecutionOut:
    steps = await _load_steps(db, execution.id)
    # 手动构建数据，避免 Pydantic 从 ORM 关系触发异步懒加载（MissingGreenlet）
    data = {
        "id": execution.id,
        "source_type": execution.source_type,
        "source_id": execution.source_id,
        "input_source": execution.input_source,
        "input_text": execution.input_text,
        "scene": execution.scene,
        "model_name": execution.model_name,
        "rule_version_id": execution.rule_version_id,
        "rule_version_code": execution.rule_version_code,
        "config_hash": execution.config_hash,
        "status": execution.status,
        "result_level": execution.result_level,
        "final_text": execution.final_text,
        "final_fields": execution.final_fields or {},
        "final_warnings": execution.final_warnings or [],
        "final_risk_items": execution.final_risk_items or [],
        "steps": steps,
    }
    return PipelineExecutionOut.model_validate(data)


async def _build_snapshot(
    db: AsyncSession,
    version: ConversionConfigVersion | None,
) -> tuple[dict[str, Any], str, list[dict[str, Any]], list[dict[str, Any]], str]:
    lexicon_rules = await load_enabled_lexicon_rules(db, version.id) if version else []
    runtime_rules = await load_enabled_runtime_rules(db, version.id) if version else []
    lexicon_mode = "replace" if version else "builtin"
    snapshot: dict[str, Any] = {
        "version": {
            "id": version.id,
            "version_code": version.version_code,
            "status": version.status,
        } if version else None,
        "lexicon_rules": lexicon_rules,
        "runtime_rules": runtime_rules,
        "lexicon_mode": lexicon_mode,
    }
    config_hash = build_config_hash(snapshot)
    return snapshot, config_hash, lexicon_rules, runtime_rules, lexicon_mode


async def _persist_step(
    db: AsyncSession,
    execution_id: int,
    config_hash: str,
    step: Any,
) -> None:
    db.add(ConversionPipelineStep(
        execution_id=execution_id,
        step_code=step.step_code,
        step_name=step.step_name,
        step_order=step.step_order,
        status=step.status,
        input_text=step.input_text,
        output_text=step.output_text,
        conversions=step.conversions,
        rule_hits=step.rule_hits,
        warnings=step.warnings,
        state_before=step.state_before,
        state_after=step.state_after,
        fields=step.fields,
        source_spans=step.source_spans,
        duration_ms=step.duration_ms,
        config_hash=config_hash,
        error_message=step.error_message,
    ))


async def _apply_final(db: AsyncSession, execution: ConversionPipelineExecution, pipeline: Any) -> None:
    execution.final_text = pipeline.normalized_text
    execution.final_fields = pipeline.fields
    execution.final_warnings = pipeline.warnings
    execution.final_risk_items = pipeline.risk_items
    execution.result_level = pipeline.result_level.value
    execution.status = "completed"


def _run_pipeline_for(
    execution: ConversionPipelineExecution,
    snapshot: dict[str, Any],
    config_hash: str,
):
    return run_pipeline(
        raw_text=execution.input_text,
        scene=execution.scene,
        model_name=execution.model_name,
        conversion_version=execution.rule_version_code or "manual",
        lexicon_rules=snapshot.get("lexicon_rules") or [],
        runtime_rules=snapshot.get("runtime_rules") or [],
        rule_mode=snapshot.get("lexicon_mode") or "builtin",
        config_hash=config_hash,
    )


@router.post("/executions", response_model=PipelineExecutionOut)
async def create_execution(data: PipelineExecutionCreate, db: AsyncSession = Depends(get_db)):
    if data.source_type == "manual":
        input_text = (data.text or "").strip()
    else:
        run = await db.get(TextValidationRun, data.source_id)
        if not run:
            raise HTTPException(status_code=404, detail="文本验证记录不存在")
        input_text = (
            run.corrected_text
            if data.input_source == "corrected_text"
            else run.raw_asr_text
        )
    if not (input_text or "").strip():
        raise HTTPException(status_code=400, detail="输入文本为空")

    version = (
        await db.get(ConversionConfigVersion, data.rule_version_id)
        if data.rule_version_id else None
    )
    snapshot, config_hash, _, _, _ = await _build_snapshot(db, version)

    execution = ConversionPipelineExecution(
        source_type=data.source_type,
        source_id=data.source_id,
        input_source=data.input_source,
        input_text=input_text,
        scene=data.scene,
        model_name=data.model_name,
        rule_version_id=version.id if version else None,
        rule_version_code=version.version_code if version else "manual",
        config_snapshot=snapshot,
        config_hash=config_hash,
        status="created",
    )
    db.add(execution)
    await db.flush()

    if data.run_mode == "run_all":
        pipeline = _run_pipeline_for(execution, snapshot, config_hash)
        for step in pipeline.steps:
            await _persist_step(db, execution.id, execution.config_hash, step)
        await _apply_final(db, execution, pipeline)

    await db.commit()
    await db.refresh(execution)
    return await _execution_out(db, execution)


@router.get("/executions/{execution_id}", response_model=PipelineExecutionOut)
async def get_execution(execution_id: int, db: AsyncSession = Depends(get_db)):
    execution = await db.get(ConversionPipelineExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return await _execution_out(db, execution)


@router.post("/executions/{execution_id}/run-step", response_model=PipelineExecutionOut)
async def run_step(
    execution_id: int,
    data: PipelineRunStepRequest,
    db: AsyncSession = Depends(get_db),
):
    execution = await db.get(ConversionPipelineExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    if execution.status == "completed":
        raise HTTPException(status_code=400, detail="所有步骤已执行完成")

    existing = await _load_steps(db, execution_id)
    existing_codes = {step.step_code for step in existing}
    snapshot = execution.config_snapshot or {}
    config_hash = execution.config_hash or build_config_hash(snapshot)

    pipeline = _run_pipeline_for(execution, snapshot, config_hash)

    next_step = next((s for s in pipeline.steps if s.step_code not in existing_codes), None)
    if next_step is None:
        raise HTTPException(status_code=400, detail="所有步骤已执行完成")
    if data.step_code != next_step.step_code:
        raise HTTPException(status_code=400, detail=f"下一步应为 {next_step.step_code}，收到 {data.step_code}")

    await _persist_step(db, execution.id, execution.config_hash, next_step)
    if len(existing_codes) + 1 >= STEP_COUNT:
        await _apply_final(db, execution, pipeline)
    else:
        execution.status = "running"
    await db.commit()
    await db.refresh(execution)
    return await _execution_out(db, execution)


@router.post("/executions/{execution_id}/fork-from-step", response_model=PipelineExecutionOut)
async def fork_from_step(
    execution_id: int,
    data: PipelineRunFromStepRequest,
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(ConversionPipelineExecution, execution_id)
    if not source:
        raise HTTPException(status_code=404, detail="原执行记录不存在")

    version = (
        await db.get(ConversionConfigVersion, data.rule_version_id)
        if data.rule_version_id else None
    )
    snapshot, config_hash, _, _, _ = await _build_snapshot(db, version)

    execution = ConversionPipelineExecution(
        source_type=source.source_type,
        source_id=source.source_id,
        input_source=source.input_source,
        input_text=source.input_text,
        scene=source.scene,
        model_name=source.model_name,
        rule_version_id=version.id if version else None,
        rule_version_code=version.version_code if version else "manual",
        config_snapshot=snapshot,
        config_hash=config_hash,
        status="created",
    )
    db.add(execution)
    await db.flush()

    pipeline = _run_pipeline_for(execution, snapshot, config_hash)
    for step in pipeline.steps:
        await _persist_step(db, execution.id, snapshot, step)
    await _apply_final(db, execution, pipeline)

    await db.commit()
    await db.refresh(execution)
    return await _execution_out(db, execution)


@router.get("/compare")
async def compare_executions(
    left_execution_id: int = Query(...),
    right_execution_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    left = await db.get(ConversionPipelineExecution, left_execution_id)
    right = await db.get(ConversionPipelineExecution, right_execution_id)
    if not left or not right:
        raise HTTPException(status_code=404, detail="执行记录不存在")

    left_hits = {
        hit.get("rule_id")
        for step in await _load_steps(db, left.id)
        for hit in step.rule_hits or []
    }
    right_hits = {
        hit.get("rule_id")
        for step in await _load_steps(db, right.id)
        for hit in step.rule_hits or []
    }

    field_changes = []
    for key in set((left.final_fields or {}).keys()) | set((right.final_fields or {}).keys()):
        left_value = (left.final_fields or {}).get(key)
        right_value = (right.final_fields or {}).get(key)
        if left_value != right_value:
            field_changes.append({
                "field_code": key,
                "left_value": left_value,
                "right_value": right_value,
            })

    return {
        "left_execution_id": left.id,
        "right_execution_id": right.id,
        "text_changed": (left.final_text or "") != (right.final_text or ""),
        "field_changes": field_changes,
        "new_rule_hits": sorted(right_hits - left_hits),
        "removed_rule_hits": sorted(left_hits - right_hits),
        "new_warnings": sorted(set(right.final_warnings or []) - set(left.final_warnings or [])),
        "removed_warnings": sorted(set(left.final_warnings or []) - set(right.final_warnings or [])),
    }
