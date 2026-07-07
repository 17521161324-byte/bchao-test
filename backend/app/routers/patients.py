"""
患者级 ASR/LLM 持久化结果路由

POST /api/patients/{patient_id}/asr/stream  SSE 流式 ASR, 保存到 patient_asr_results
GET  /api/patients/{patient_id}/asr-results
GET  /api/patients/{patient_id}/asr-current
PUT  /api/patients/{patient_id}/asr-results/{result_id}/current

POST /api/patients/{patient_id}/llm/run      LLM 结构化提取, 保存到 patient_llm_results
GET  /api/patients/{patient_id}/llm-results
GET  /api/patients/{patient_id}/llm-current
PUT  /api/patients/{patient_id}/llm-results/{result_id}/current
"""
import asyncio
import json
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from loguru import logger

from app.config import resolve_hotwords
from app.database import get_db
from app.models import (
    PatientRecord, AudioSeg, ModelConfig,
    PatientAsrResult, PatientLlmResult,
)
from app.services.asr import create_asr

router = APIRouter()


# ------------------------------------------------------------------
# 辅助: 设置 is_current
# ------------------------------------------------------------------

async def _set_current_asr(db: AsyncSession, patient_id: int, current_id: int):
    """将指定 ASR 结果设为当前, 同 patient 其他设为 False"""
    await db.execute(
        update(PatientAsrResult)
        .where(PatientAsrResult.patient_id == patient_id)
        .values(is_current=False)
    )
    await db.execute(
        update(PatientAsrResult)
        .where(PatientAsrResult.id == current_id)
        .values(is_current=True)
    )
    await db.commit()


async def _set_current_llm(db: AsyncSession, patient_id: int, current_id: int):
    await db.execute(
        update(PatientLlmResult)
        .where(PatientLlmResult.patient_id == patient_id)
        .values(is_current=False)
    )
    await db.execute(
        update(PatientLlmResult)
        .where(PatientLlmResult.id == current_id)
        .values(is_current=True)
    )
    await db.commit()


# ------------------------------------------------------------------
# ASR 接口
# ------------------------------------------------------------------

@router.get("/{patient_id}/asr/stream")
async def patient_asr_stream(
    patient_id: int,
    asr_model_id: int,
    hotwords: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """患者级 SSE 流式 ASR, 结果持久化到 patient_asr_results"""
    # 读取 patient (预加载 date_folder)
    patient_result = await db.execute(
        select(PatientRecord)
        .options(selectinload(PatientRecord.date_folder))
        .where(PatientRecord.id == patient_id)
    )
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail=f"患者 {patient_id} 不存在")

    # 读取 segs
    segs_result = await db.execute(
        select(AudioSeg).where(AudioSeg.patient_id == patient_id).order_by(AudioSeg.seg_index)
    )
    segs = [
        {"seg_index": s.seg_index, "file_path": s.file_path, "duration": s.duration}
        for s in segs_result.scalars().all()
    ]
    if not segs:
        raise HTTPException(status_code=400, detail="该患者无录音文件")

    # 读取模型
    asr_model = await db.get(ModelConfig, asr_model_id)
    if not asr_model:
        raise HTTPException(status_code=404, detail="ASR 模型不存在")

    # 解析热词
    parsed_hotwords = [w.strip() for w in hotwords.split(",")] if hotwords else None
    resolved_hotwords = resolve_hotwords(parsed_hotwords, asr_model.params)

    # 创建 running 状态记录(asr_model_name 用模型名快照)
    record = PatientAsrResult(
        patient_id=patient_id,
        record_id=patient.record_id,
        date=patient.date_folder.date if patient.date_folder else None,
        asr_model_id=asr_model_id,
        asr_model_name=asr_model.name,
        provider=asr_model.provider,
        hotwords=resolved_hotwords or [],
        status="running",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    # 使用 create_asr 工厂 (与实验链路一致)
    asr = create_asr(
        asr_model.provider,
        **{
            "endpoint": asr_model.endpoint,
            "api_key": asr_model.api_key,
            "api_secret": asr_model.api_secret,
            "secret_key": asr_model.secret_key,
            "model_name": asr_model.model_name,
        },
    )

    async def event_generator():
        start = time.time()
        asr_results = []
        try:
            yield f"event: progress\ndata: {json.dumps({'stage': 'progress', 'total': len(segs), 'started': True}, ensure_ascii=False)}\n\n"

            for seg in segs:
                yield f"event: progress\ndata: {json.dumps({'stage': 'segment_start', 'seg_index': seg['seg_index'], 'total': len(segs)}, ensure_ascii=False)}\n\n"

                text = await asr.transcribe(seg["file_path"], hotwords=resolved_hotwords)
                asr_results.append({"seg_index": seg["seg_index"], "text": text, "duration": seg["duration"]})

                yield f"event: segment\ndata: {json.dumps({'stage': 'segment', 'seg_index': seg['seg_index'], 'text': text, 'duration': seg['duration']}, ensure_ascii=False)}\n\n"

            full_transcript = "\n".join(r["text"] for r in asr_results)
            duration = round(time.time() - start, 2)

            # 成功: 更新记录
            record.segments = asr_results
            record.full_transcript = full_transcript
            record.duration_seconds = duration
            record.status = "success"
            await db.commit()

            # 设为当前 (事务关闭后,避免悬挂)
            await _set_current_asr(db, patient_id, record.id)

            yield f"event: complete\ndata: {json.dumps({'stage': 'complete', 'result_id': record.id, **_asr_response(record)}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"患者 {patient_id} ASR 失败: {e}")
            try:
                record.status = "failed"
                record.error_message = str(e)
                await db.commit()
            except Exception:
                pass
            yield f"event: error\ndata: {json.dumps({'stage': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{patient_id}/asr-results")
async def list_patient_asr_results(patient_id: int, db: AsyncSession = Depends(get_db)):
    """返回某患者所有 ASR 历史"""
    result = await db.execute(
        select(PatientAsrResult)
        .where(PatientAsrResult.patient_id == patient_id)
        .order_by(PatientAsrResult.created_at.desc())
    )
    return [_asr_response(r) for r in result.scalars().all()]


@router.get("/{patient_id}/asr-current")
async def get_patient_asr_current(patient_id: int, db: AsyncSession = Depends(get_db)):
    """返回当前采用的 ASR 结果"""
    result = await db.execute(
        select(PatientAsrResult)
        .where(PatientAsrResult.patient_id == patient_id, PatientAsrResult.is_current == True)
    )
    record = result.scalar_one_or_none()
    return _asr_response(record) if record else None


def _asr_response(r: PatientAsrResult) -> dict:
    """构建兼容前端旧字段的响应"""
    return {
        "id": r.id,
        "patient_id": r.patient_id,
        "record_id": r.record_id,
        "date": r.date,
        "asr_model_id": r.asr_model_id,
        "model_name": r.asr_model_name or "",  # 前端旧字段
        "full_model_name": r.asr_model_name,
        "provider": r.provider,
        "segments": r.segments,
        "full_transcript": r.full_transcript,
        "duration_seconds": r.duration_seconds,
        "status": r.status,
        "error_message": r.error_message,
        "is_current": r.is_current,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _llm_response(r: PatientLlmResult) -> dict:
    return {
        "id": r.id,
        "patient_id": r.patient_id,
        "asr_result_id": r.asr_result_id,
        "llm_model_id": r.llm_model_id,
        "model_name": r.llm_model_name or "",  # 前端旧字段
        "full_model_name": r.llm_model_name,
        "structured": r.structured_result,        # 前端旧字段
        "structured_result": r.structured_result,
        "summary": r.summary_text,                # 前端旧字段
        "summary_text": r.summary_text,
        "raw_text": r.raw_output,                 # 前端旧字段
        "raw_output": r.raw_output,
        "evaluation": r.evaluation,
        "accuracy": r.accuracy,
        "status": r.status,
        "error_message": r.error_message,
        "is_current": r.is_current,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.put("/{patient_id}/asr-results/{result_id}/current")
async def set_patient_asr_current(
    patient_id: int,
    result_id: int,
    db: AsyncSession = Depends(get_db),
):
    """切换当前 ASR 结果"""
    record = await db.get(PatientAsrResult, result_id)
    if not record or record.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    await _set_current_asr(db, patient_id, result_id)
    return {"ok": True}


# ------------------------------------------------------------------
# LLM 接口
# ------------------------------------------------------------------

@router.post("/{patient_id}/llm/run")
async def patient_llm_run(
    patient_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """患者级 LLM 结构化提取, 保存到 patient_llm_results"""
    llm_model_id = body.get("llm_model_id")
    asr_result_id = body.get("asr_result_id")  # 可选, 默认当前
    prompt_content = body.get("prompt_content")

    patient = await db.get(PatientRecord, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"患者 {patient_id} 不存在")

    # 确定 ASR 结果
    asr_record = None
    if asr_result_id:
        asr_record = await db.get(PatientAsrResult, asr_result_id)
    else:
        # 默认取当前
        result = await db.execute(
            select(PatientAsrResult)
            .where(PatientAsrResult.patient_id == patient_id, PatientAsrResult.is_current == True)
        )
        asr_record = result.scalar_one_or_none()

    transcript = asr_record.full_transcript if asr_record else ""
    if not transcript:
        raise HTTPException(status_code=400, detail="无 ASR 转写文本可用")

    # 读取 LLM 模型
    if not llm_model_id:
        raise HTTPException(status_code=400, detail="请提供 llm_model_id")
    llm_model = await db.get(ModelConfig, llm_model_id)
    if not llm_model:
        raise HTTPException(status_code=404, detail="LLM 模型不存在")

    # 创建 running 记录
    record = PatientLlmResult(
        patient_id=patient_id,
        asr_result_id=asr_record.id if asr_record else None,
        llm_model_id=llm_model_id,
        llm_model_name=llm_model.name,
        prompt_content=prompt_content,
        status="running",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    executor = TestExecutor()
    try:
        llm_result = await executor.execute_llm(
            transcript=transcript,
            llm_provider=llm_model.provider,
            llm_config={
                "endpoint": llm_model.endpoint,
                "api_key": llm_model.api_key,
                "api_secret": llm_model.api_secret,
                "model_name": llm_model.model_name,
            },
            prompt_template=prompt_content,
        )
        record.structured_result = llm_result["structured_result"]
        record.summary_text = llm_result["summary_text"]
        record.raw_output = llm_result["llm_raw_output"]
        record.status = "success"

        # 评估
        if record.structured_result:
            from sqlalchemy import select as sa_select
            from app.models import BUltraResult
            from app.services.parser import evaluate_result
            gt_r = await db.execute(
                sa_select(BUltraResult).where(BUltraResult.patient_id == patient_id)
            )
            gt = gt_r.scalar_one_or_none()
            if gt:
                evaluation = evaluate_result(
                    identified=record.structured_result,
                    ground_truth={
                        "right_follicle_total": gt.right_follicle_total,
                        "left_follicle_total": gt.left_follicle_total,
                        "endometrium_thickness": gt.endometrium_thickness,
                        "endometrium_type": gt.endometrium_type,
                        "right_ovary_length": gt.right_ovary_length,
                        "right_ovary_width": gt.right_ovary_width,
                        "left_ovary_length": gt.left_ovary_length,
                        "left_ovary_width": gt.left_ovary_width,
                    },
                )
                record.evaluation = evaluation
                record.accuracy = evaluation.get("accuracy")

        await db.commit()
        await _set_current_llm(db, patient_id, record.id)
    except Exception as e:
        logger.error(f"患者 {patient_id} LLM 失败: {e}")
        record.status = "failed"
        record.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))

    return _llm_response(record)


@router.get("/{patient_id}/llm-results")
async def list_patient_llm_results(patient_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PatientLlmResult)
        .where(PatientLlmResult.patient_id == patient_id)
        .order_by(PatientLlmResult.created_at.desc())
    )
    return [_llm_response(r) for r in result.scalars().all()]


@router.get("/{patient_id}/llm-current")
async def get_patient_llm_current(patient_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PatientLlmResult)
        .where(PatientLlmResult.patient_id == patient_id, PatientLlmResult.is_current == True)
    )
    record = result.scalar_one_or_none()
    return _llm_response(record) if record else None


@router.put("/{patient_id}/llm-results/{result_id}/current")
async def set_patient_llm_current(
    patient_id: int,
    result_id: int,
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(PatientLlmResult, result_id)
    if not record or record.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    await _set_current_llm(db, patient_id, result_id)
    return {"ok": True}
