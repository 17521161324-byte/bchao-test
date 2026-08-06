"""流水线调试 API（Task 15 + P0 扩展）。

前缀 /api/conversion-pipeline：
- POST /executions（创建执行，run_mode=create_only|run_all）
- GET  /executions（列表：source_type/source_id/rule_version_id/limit）
- GET  /executions/{id}
- POST /executions/{id}/run-step（单步，只能执行下一步，用冻结 config_snapshot）
- POST /executions/{id}/run-to-step（执行到指定步骤后停止）
- PATCH /executions/{id}/steps/{step_code}/output（人工修订步骤输出）
- POST /executions/{id}/continue（从指定步骤有效输出继续）
- POST /executions/{id}/fork-from-step（新规则版本完整重跑，方案 B：记录血缘不改旧执行）
- GET  /compare?left_execution_id=&right_execution_id=
"""
from __future__ import annotations

from datetime import datetime
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
    PipelineContinueRequest,
    PipelineExecutionCreate,
    PipelineExecutionOut,
    PipelineRunFromStepRequest,
    PipelineRunStepRequest,
    PipelineRunToStepRequest,
    PipelineStepOutputPatch,
    PipelineStepOut,
    PipelineStepPatchOut,
)
from app.services.conversion_config import (
    load_enabled_lexicon_rules,
    load_enabled_runtime_rules,
)
from app.services.conversion_pipeline.orchestrator import build_config_hash, run_pipeline
from app.services.conversion_pipeline.types import STEP_ORDER, StepCode

router = APIRouter()

STEP_COUNT = 7

_STEP_ORDER_BY_CODE = {code.value: order for code, order in STEP_ORDER.items()}
_CODES_BY_ORDER = sorted(STEP_ORDER, key=lambda code: STEP_ORDER[code])


def _next_step_code(step_code: str) -> StepCode | None:
    order = _STEP_ORDER_BY_CODE.get(step_code)
    if order is None:
        return None
    for code in _CODES_BY_ORDER:
        if STEP_ORDER[code] > order:
            return code
    return None


def _validate_step_code(step_code: str) -> StepCode:
    if step_code not in _STEP_ORDER_BY_CODE:
        raise HTTPException(status_code=400, detail=f"无效的步骤编码: {step_code}")
    return StepCode(step_code)


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
        "parent_execution_id": execution.parent_execution_id,
        "fork_step_code": execution.fork_step_code,
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
        state_transitions=step.state_transitions,
        fields=step.fields,
        source_spans=step.source_spans,
        duration_ms=step.duration_ms,
        config_hash=config_hash,
        error_message=step.error_message,
        system_output_text=step.output_text,
        effective_output_text=step.output_text,
    ))


async def _apply_final(db: AsyncSession, execution: ConversionPipelineExecution, pipeline: Any) -> None:
    execution.final_text = pipeline.normalized_text
    execution.final_fields = pipeline.fields
    execution.final_warnings = pipeline.warnings
    execution.final_risk_items = pipeline.risk_items
    execution.result_level = pipeline.result_level.value
    # P0-04：步骤失败时执行状态必须标记 failed，不得显示 completed
    if any(step.status == "failed" for step in pipeline.steps):
        execution.status = "failed"
    else:
        execution.status = "completed"


def _run_pipeline_for(
    execution: ConversionPipelineExecution,
    snapshot: dict[str, Any],
    config_hash: str,
    *,
    start_step: StepCode | str | None = None,
    stop_after_step: StepCode | str | None = None,
    initial_text: str | None = None,
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
        start_step=start_step,
        stop_after_step=stop_after_step,
        initial_text=initial_text,
    )


async def _resolve_version_or_404(
    db: AsyncSession,
    rule_version_id: int | None,
) -> ConversionConfigVersion | None:
    if not rule_version_id:
        return None
    version = await db.get(ConversionConfigVersion, rule_version_id)
    if not version:
        # P1-05：不存在的规则版本 ID 返回 404，不静默回退 manual/builtin
        raise HTTPException(status_code=404, detail="规则版本不存在")
    return version


@router.get("/executions", response_model=list[PipelineExecutionOut])
async def list_executions(
    source_type: str | None = Query(default=None),
    source_id: int | None = Query(default=None),
    rule_version_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """执行记录列表（供前端重构使用）。"""
    query = select(ConversionPipelineExecution).order_by(
        ConversionPipelineExecution.id.desc()
    )
    if source_type:
        query = query.where(ConversionPipelineExecution.source_type == source_type)
    if source_id is not None:
        query = query.where(ConversionPipelineExecution.source_id == source_id)
    if rule_version_id is not None:
        query = query.where(ConversionPipelineExecution.rule_version_id == rule_version_id)
    rows = (await db.execute(query.limit(limit))).scalars().all()
    return [await _execution_out(db, row) for row in rows]


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

    version = await _resolve_version_or_404(db, data.rule_version_id)
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
    elif next_step.status == "failed":
        execution.status = "failed"
    else:
        execution.status = "running"
    await db.commit()
    await db.refresh(execution)
    return await _execution_out(db, execution)


@router.post("/executions/{execution_id}/run-to-step", response_model=PipelineExecutionOut)
async def run_to_step(
    execution_id: int,
    data: PipelineRunToStepRequest,
    db: AsyncSession = Depends(get_db),
):
    """从最近有效步骤执行到指定步骤后停止（供前端逐步执行/执行到指定步骤）。"""
    target = _validate_step_code(data.step_code)
    execution = await db.get(ConversionPipelineExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    if execution.status == "completed":
        raise HTTPException(status_code=400, detail="所有步骤已执行完成")

    existing = await _load_steps(db, execution_id)
    snapshot = execution.config_snapshot or {}
    config_hash = execution.config_hash or build_config_hash(snapshot)

    if existing:
        last = max(existing, key=lambda step: step.step_order)
        if _STEP_ORDER_BY_CODE[last.step_code] >= _STEP_ORDER_BY_CODE[target.value]:
            raise HTTPException(status_code=400, detail=f"指定步骤 {target.value} 已执行")
        start_step = _next_step_code(last.step_code)
        initial_text = last.effective_output_text or last.output_text
    else:
        start_step = None
        initial_text = None

    pipeline = _run_pipeline_for(
        execution, snapshot, config_hash,
        start_step=start_step, stop_after_step=target, initial_text=initial_text,
    )
    for step in pipeline.steps:
        await _persist_step(db, execution.id, execution.config_hash, step)

    if any(step.status == "failed" for step in pipeline.steps):
        execution.status = "failed"
    elif target == StepCode.RISK_INTERCEPT:
        await _apply_final(db, execution, pipeline)
    else:
        execution.status = "running"
    await db.commit()
    await db.refresh(execution)
    return await _execution_out(db, execution)


@router.patch(
    "/executions/{execution_id}/steps/{step_code}/output",
    response_model=PipelineStepPatchOut,
)
async def patch_step_output(
    execution_id: int,
    step_code: str,
    data: PipelineStepOutputPatch,
    db: AsyncSession = Depends(get_db),
):
    """人工修订步骤输出：写 manual/effective 输出，并返回被失效的后续步骤编码。"""
    execution = await db.get(ConversionPipelineExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    step = (
        await db.execute(
            select(ConversionPipelineStep).where(
                ConversionPipelineStep.execution_id == execution_id,
                ConversionPipelineStep.step_code == step_code,
            )
        )
    ).scalar_one_or_none()
    if not step:
        raise HTTPException(status_code=404, detail="步骤不存在")

    step.manual_output_text = data.manual_output_text
    step.effective_output_text = data.manual_output_text
    step.edited = 1
    step.edited_by = "manual"
    step.edited_at = datetime.utcnow()
    step.edit_note = data.edit_note

    # 后续步骤输出基于旧文本，全部失效并删除（重新执行时重建）
    later = await _load_steps(db, execution_id)
    invalidated = [item for item in later if item.step_order > step.step_order]
    for item in invalidated:
        await db.delete(item)

    await db.commit()
    await db.refresh(step)
    return PipelineStepPatchOut(
        step=PipelineStepOut.model_validate(step),
        invalidated_step_codes=[item.step_code for item in invalidated],
    )


@router.post("/executions/{execution_id}/continue", response_model=PipelineExecutionOut)
async def continue_execution(
    execution_id: int,
    data: PipelineContinueRequest,
    db: AsyncSession = Depends(get_db),
):
    """用指定步骤的有效输出继续执行后续步骤（run_mode=run_all 跑完 / run_step 只跑下一步）。"""
    execution = await db.get(ConversionPipelineExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    if execution.status == "completed":
        raise HTTPException(status_code=400, detail="执行已完成")

    existing = await _load_steps(db, execution_id)
    base = next((item for item in existing if item.step_code == data.from_step_code), None)
    if base is None:
        raise HTTPException(status_code=400, detail=f"起始步骤 {data.from_step_code} 尚未执行")

    # 删除起始步骤之后的旧步骤（输出已变化，重新生成）
    for item in existing:
        if item.step_order > base.step_order:
            await db.delete(item)

    snapshot = execution.config_snapshot or {}
    config_hash = execution.config_hash or build_config_hash(snapshot)
    start_step = _next_step_code(base.step_code)
    if start_step is None:
        raise HTTPException(status_code=400, detail="起始步骤已是最后一步")

    initial_text = base.effective_output_text or base.output_text
    stop_after = start_step if data.run_mode == "run_step" else None
    pipeline = _run_pipeline_for(
        execution, snapshot, config_hash,
        start_step=start_step, stop_after_step=stop_after, initial_text=initial_text,
    )
    for step in pipeline.steps:
        await _persist_step(db, execution.id, execution.config_hash, step)

    if any(step.status == "failed" for step in pipeline.steps):
        execution.status = "failed"
    elif data.run_mode == "run_all" and stop_after is None:
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
    """fork（方案 B，P0-05）：新建执行并从原始输入完整重跑。

    step_code 仅记录为 fork_step_code（重点比较起始步骤），不复制/修改旧执行；
    血缘通过 parent_execution_id 记录。
    """
    _validate_step_code(data.step_code)
    source = await db.get(ConversionPipelineExecution, execution_id)
    if not source:
        raise HTTPException(status_code=404, detail="原执行记录不存在")

    version = await _resolve_version_or_404(db, data.rule_version_id)
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
        parent_execution_id=source.id,
        fork_step_code=data.step_code,
        status="created",
    )
    db.add(execution)
    await db.flush()

    pipeline = _run_pipeline_for(execution, snapshot, config_hash)
    for step in pipeline.steps:
        await _persist_step(db, execution.id, execution.config_hash, step)
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
