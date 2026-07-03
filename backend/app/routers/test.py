"""
测试执行路由（含 SSE 流式进度）
"""
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from loguru import logger

from app.database import get_db
from app.models import PatientRecord, AudioSeg, ModelConfig, TestRun, BUltraResult
from app.schemas import TestStartRequest, TestResultOut, EvaluationUpdate
from app.services.test_executor import TestExecutor
from app.services.parser import evaluate_result

router = APIRouter()


@router.get("/history", response_model=list[TestResultOut])
async def list_test_history(
    record_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """获取测试历史列表"""
    query = select(TestRun).order_by(TestRun.created_at.desc()).offset(skip).limit(limit)
    if record_id:
        query = query.where(TestRun.record_id == record_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/start")
async def start_test(
    record_id: str = Query(...),
    asr_model_id: int = Query(...),
    llm_model_id: int | None = Query(None),
    prompt_version: str = Query("v1.0"),
    prompt_template: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """
    启动单条测试（返回 SSE 流实时推送进度）
    使用 GET 查询参数，兼容浏览器 EventSource
    """
    # 查找病历
    result = await db.execute(
        select(PatientRecord)
        .options(selectinload(PatientRecord.segs), selectinload(PatientRecord.date_folder))
        .where(PatientRecord.record_id == record_id)
        .order_by(PatientRecord.id)
    )
    patients = result.scalars().all()
    if not patients:
        raise HTTPException(status_code=404, detail=f"病历号 {record_id} 不存在")
    patient = patients[0]

    if not patient.segs:
        raise HTTPException(status_code=400, message="该病历无录音文件")

    # 查找 ASR 模型
    asr_result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == asr_model_id)
    )
    asr_model = asr_result.scalar_one_or_none()
    if not asr_model:
        raise HTTPException(status_code=404, message="ASR 模型不存在")

    # 查找 LLM 模型（可选）
    llm_model = None
    if llm_model_id:
        llm_result = await db.execute(
            select(ModelConfig).where(ModelConfig.id == llm_model_id)
        )
        llm_model = llm_result.scalar_one_or_none()

    # 准备 seg 数据
    segs = [
        {
            "seg_index": s.seg_index,
            "file_path": s.file_path,
            "duration": s.duration,
        }
        for s in sorted(patient.segs, key=lambda x: x.seg_index)
    ]

    # 创建测试记录
    from app.models import DateFolder
    date_str = ""
    if patient.date_folder:
        date_str = patient.date_folder.date

    test_run = TestRun(
        record_id=record_id,
        date=date_str,
        asr_model_id=asr_model.id,
        llm_model_id=llm_model.id if llm_model else None,
        prompt_version=prompt_version,
        asr_results=[],
        full_transcript="",
    )
    db.add(test_run)
    await db.commit()
    await db.refresh(test_run)

    async def event_generator():
        executor = TestExecutor()
        queue = asyncio.Queue()

        async def on_progress(event):
            await queue.put(event)

        # 构造配置
        asr_config = {
            "endpoint": asr_model.endpoint,
            "api_key": asr_model.api_key,
            "api_secret": asr_model.api_secret,
            "model_name": asr_model.model_name,
        }
        llm_config = None
        if llm_model:
            llm_config = {
                "endpoint": llm_model.endpoint,
                "api_key": llm_model.api_key,
                "api_secret": llm_model.api_secret,
                "model_name": llm_model.model_name,
            }

        async def run_test():
            try:
                result_data = await executor.execute(
                    segs=segs,
                    asr_provider=asr_model.provider,
                    asr_config=asr_config,
                    llm_provider=llm_model.provider if llm_model else None,
                    llm_config=llm_config,
                    prompt_template=prompt_template,
                    progress_callback=on_progress,
                )

                # 更新测试记录
                test_run.asr_results = result_data["asr_results"]
                test_run.full_transcript = result_data["full_transcript"]
                test_run.llm_raw_output = result_data["llm_raw_output"]
                test_run.structured_result = result_data["structured_result"]
                test_run.summary_text = result_data["summary_text"]
                test_run.duration_seconds = result_data["duration_seconds"]

                # 自动评估（如果有 ground truth）
                gt_result = await db.execute(
                    select(BUltraResult).where(BUltraResult.patient_id == patient.id)
                )
                gt = gt_result.scalar_one_or_none()
                if gt and test_run.structured_result:
                    evaluation = evaluate_result(
                        identified=test_run.structured_result,
                        ground_truth={
                            "right_follicle_total": gt.right_follicle_total,
                            "left_follicle_total": gt.left_follicle_total,
                            "endometrium_thickness": gt.endometrium_thickness,
                            "endometrium_type": gt.endometrium_type,
                            "right_ovary_length": gt.right_ovary_length,
                            "right_ovary_width": gt.right_ovary_width,
                            "left_ovary_length": gt.left_ovary_length,
                            "left_ovary_width": gt.left_ovary_width,
                        }
                    )
                    test_run.evaluation = evaluation
                    test_run.accuracy = evaluation.get("accuracy")

                await db.commit()
                await queue.put({"stage": "complete", "test_id": test_run.id, "status": "ok"})
            except Exception as e:
                logger.error(f"测试执行失败: {e}")
                await queue.put({"stage": "error", "message": str(e)})
            finally:
                await queue.put(None)  # Sentinel to stop generator

        # Start test execution in background
        task = asyncio.create_task(run_test())

        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=300)
                if event is None:
                    break
                if event["stage"] == "complete":
                    yield f"event: complete\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    break
                elif event["stage"] == "error":
                    yield f"event: error\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    break
                else:
                    yield f"event: progress\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{test_id}", response_model=TestResultOut)
async def get_test_result(test_id: int, db: AsyncSession = Depends(get_db)):
    """获取测试结果"""
    result = await db.execute(select(TestRun).where(TestRun.id == test_id))
    test = result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="测试记录不存在")
    return test


@router.put("/{test_id}/evaluate", response_model=TestResultOut)
async def update_evaluation(
    test_id: int,
    data: EvaluationUpdate,
    db: AsyncSession = Depends(get_db),
):
    """提交人工修正评估"""
    result = await db.execute(select(TestRun).where(TestRun.id == test_id))
    test = result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="测试记录不存在")

    test.structured_result = data.structured_result
    test.human_corrected = data.human_corrected

    # 重新评估
    patient = await db.execute(
        select(PatientRecord).where(PatientRecord.record_id == test.record_id)
    )
    patient_obj = patient.scalar_one_or_none()
    if patient_obj:
        gt_result = await db.execute(
            select(BUltraResult).where(BUltraResult.patient_id == patient_obj.id)
        )
        gt = gt_result.scalar_one_or_none()
        if gt:
            evaluation = evaluate_result(
                identified=data.structured_result,
                ground_truth={
                    "right_follicle_total": gt.right_follicle_total,
                    "left_follicle_total": gt.left_follicle_total,
                    "endometrium_thickness": gt.endometrium_thickness,
                    "endometrium_type": gt.endometrium_type,
                    "right_ovary_length": gt.right_ovary_length,
                    "right_ovary_width": gt.right_ovary_width,
                    "left_ovary_length": gt.left_ovary_length,
                    "left_ovary_width": gt.left_ovary_width,
                }
            )
            test.evaluation = evaluation
            test.accuracy = evaluation.get("accuracy")

    await db.commit()
    await db.refresh(test)
    return test
