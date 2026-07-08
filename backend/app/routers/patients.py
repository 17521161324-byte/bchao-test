"""
检查记录级 ASR/LLM 持久化结果路由

业务语义说明:
- 本模块所有 patient_id 实际为 exam_record_id (= patient_records.id)
- record_id (病历号) 可跨日期重复, 不能作为结果关联键
- 每个检查记录 (exam_record) 有独立的 ASR/LLM 结果

GET  /api/patients/{patient_id}/asr/stream    SSE 流式 ASR, 保存到 patient_asr_results
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
import io
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from loguru import logger

from app.config import resolve_hotwords
from app.database import get_db, AsyncSessionLocal
from app.models import (
    PatientRecord, AudioSeg, ModelConfig,
    PatientAsrResult, PatientLlmResult,
)
from app.services.asr import create_asr
from app.services.test_executor import TestExecutor

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
    """患者级 SSE 流式 ASR, 结果持久化到 patient_asr_results

    前置阶段只读取必要快照 (plain dict), 避免跨 stream 长期持有 ORM 对象。
    event_generator 内部使用独立 AsyncSessionLocal, 确保流式期间 DB 操作可靠。
    """
    # === 前置阶段: 读取必要快照 (不把 ORM 对象传进 generator) ===
    patient_result = await db.execute(
        select(PatientRecord)
        .options(selectinload(PatientRecord.date_folder))
        .where(PatientRecord.id == patient_id)
    )
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail=f"患者 {patient_id} 不存在")

    segs_result = await db.execute(
        select(AudioSeg).where(AudioSeg.patient_id == patient_id).order_by(AudioSeg.seg_index)
    )
    segs = [
        {"seg_index": s.seg_index, "file_path": s.file_path, "duration": s.duration}
        for s in segs_result.scalars().all()
    ]
    if not segs:
        raise HTTPException(status_code=400, detail="该患者无录音文件")

    asr_model = await db.get(ModelConfig, asr_model_id)
    if not asr_model:
        raise HTTPException(status_code=404, detail="ASR 模型不存在")

    parsed_hotwords = [w.strip() for w in hotwords.split(",")] if hotwords else None
    resolved_hotwords = resolve_hotwords(parsed_hotwords, asr_model.params)

    # 快照所有需要的纯数据 (不传 ORM 对象进 generator)
    snap_patient_id = patient_id
    snap_record_id = patient.record_id
    snap_date = patient.date_folder.date if patient.date_folder else None
    snap_asr_model_id = asr_model_id
    snap_asr_model_name = asr_model.name
    snap_provider = asr_model.provider
    snap_hotwords = resolved_hotwords or []
    snap_asr_config = {
        "endpoint": asr_model.endpoint,
        "api_key": asr_model.api_key,
        "api_secret": asr_model.api_secret,
        "secret_key": asr_model.secret_key,
        "model_name": asr_model.model_name,
    }

    async def event_generator():
        # === 独立 session, 不依赖请求级 db ===
        async with AsyncSessionLocal() as stream_db:
            record_id_internal = None
            try:
                # 创建 running 记录
                record = PatientAsrResult(
                    patient_id=snap_patient_id,
                    record_id=snap_record_id,
                    date=snap_date,
                    asr_model_id=snap_asr_model_id,
                    asr_model_name=snap_asr_model_name,
                    provider=snap_provider,
                    hotwords=snap_hotwords,
                    status="running",
                )
                stream_db.add(record)
                await stream_db.commit()
                await stream_db.refresh(record)
                record_id_internal = record.id

                yield f"event: progress\ndata: {json.dumps({'stage': 'progress', 'total': len(segs), 'started': True}, ensure_ascii=False)}\n\n"

                # 使用独立 asr 实例
                asr = create_asr(snap_provider, **snap_asr_config)
                start = time.time()
                asr_results = []

                for seg in segs:
                    yield f"event: progress\ndata: {json.dumps({'stage': 'segment_start', 'seg_index': seg['seg_index'], 'total': len(segs)}, ensure_ascii=False)}\n\n"

                    text = await asr.transcribe(seg["file_path"], hotwords=snap_hotwords)
                    asr_results.append({"seg_index": seg["seg_index"], "text": text, "duration": seg["duration"]})

                    yield f"event: segment\ndata: {json.dumps({'stage': 'segment', 'seg_index': seg['seg_index'], 'text': text, 'duration': seg['duration']}, ensure_ascii=False)}\n\n"

                full_transcript = "\n".join(r["text"] for r in asr_results)
                duration_val = round(time.time() - start, 2)

                # 重新获取记录并更新 (避免悬挂 ORM)
                record = await stream_db.get(PatientAsrResult, record_id_internal)
                record.segments = asr_results
                record.full_transcript = full_transcript
                record.duration_seconds = duration_val
                record.status = "success"
                record.is_current = True
                await stream_db.commit()

                # 同 patient 其他 ASR 设为 not current
                await stream_db.execute(
                    update(PatientAsrResult)
                    .where(
                        PatientAsrResult.patient_id == snap_patient_id,
                        PatientAsrResult.id != record_id_internal,
                    )
                    .values(is_current=False)
                )
                await stream_db.commit()

                # commit 成功后再发送 complete
                yield f"event: complete\ndata: {json.dumps({'stage': 'complete', 'result_id': record_id_internal, **_asr_response(record)}, ensure_ascii=False)}\n\n"

            except asyncio.CancelledError:
                # 客户端中断 (关闭页面 / 网络断开)
                logger.warning(f"患者 {snap_patient_id} ASR SSE 连接中断")
                try:
                    if record_id_internal:
                        record = await stream_db.get(PatientAsrResult, record_id_internal)
                        record.status = "failed"
                        record.error_message = "SSE 连接中断或客户端取消"
                        await stream_db.commit()
                except Exception:
                    pass
                yield f"event: error\ndata: {json.dumps({'stage': 'error', 'message': '连接中断'}, ensure_ascii=False)}\n\n"

            except Exception as e:
                logger.error(f"患者 {snap_patient_id} ASR 失败: {e}")
                try:
                    if record_id_internal:
                        record = await stream_db.get(PatientAsrResult, record_id_internal)
                        record.status = "failed"
                        record.error_message = str(e)
                        await stream_db.commit()
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
        "exam_record_id": r.patient_id,  # patient_id 实际是 exam_record_id
        "patient_id": r.patient_id,      # 保留兼容
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
        "exam_record_id": r.patient_id,  # patient_id 实际是 exam_record_id
        "patient_id": r.patient_id,      # 保留兼容
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
    prompt_template_id = body.get("prompt_template_id")  # 可选

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

    # 尝试获取提示词模板信息
    prompt_template_name = None
    if prompt_template_id:
        from app.models import PromptTemplate
        tmpl = await db.get(PromptTemplate, prompt_template_id)
        if tmpl:
            prompt_template_name = tmpl.name

    # 创建 running 记录
    record = PatientLlmResult(
        patient_id=patient_id,
        asr_result_id=asr_record.id if asr_record else None,
        llm_model_id=llm_model_id,
        llm_model_name=llm_model.name,
        prompt_template_id=prompt_template_id,
        prompt_template_name=prompt_template_name,
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
        record.raw_output = llm_result["llm_raw_output"]
        record.prompt_content = prompt_content  # 保存实际使用的提示词
        record.status = "success"

        # summary_text 优先取 structured 中的 summary 字段
        structured = llm_result.get("structured_result") or {}
        if structured.get("summary"):
            record.summary_text = str(structured["summary"])
        elif llm_result.get("summary_text"):
            record.summary_text = llm_result["summary_text"]
        else:
            record.summary_text = ""

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


@router.delete("/{patient_id}/llm-results")
async def clear_patient_llm_results(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
):
    """清空当前检查记录的全部 LLM 历史记录"""
    from sqlalchemy import delete

    patient = await db.get(PatientRecord, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"检查记录 {patient_id} 不存在")

    result = await db.execute(
        delete(PatientLlmResult).where(PatientLlmResult.patient_id == patient_id)
    )
    deleted = result.rowcount
    await db.commit()
    return {"ok": True, "deleted": deleted}


@router.get("/{patient_id}/llm-results/export")
async def export_patient_llm_results(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
):
    """导出当前检查记录的全部 LLM 历史 + ASR + 真实B超 + 提示词模板 为 Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from sqlalchemy import select
    from app.models import DateFolder, BUltraResult, PromptTemplate, PatientAsrResult

    result = await db.execute(
        select(PatientLlmResult, PatientRecord, DateFolder)
        .join(PatientRecord, PatientLlmResult.patient_id == PatientRecord.id)
        .outerjoin(DateFolder, PatientRecord.date_folder_id == DateFolder.id)
        .where(PatientLlmResult.patient_id == patient_id)
        .order_by(PatientLlmResult.created_at.asc())
    )
    rows = result.all()

    if not rows:
        raise HTTPException(status_code=404, detail="无 LLM 结果")

    patient = rows[0][1] if rows else None
    date_folder = rows[0][2] if rows else None
    record_id = patient.record_id if patient else f"exam_{patient_id}"
    date_str = date_folder.date if date_folder else ""

    # 获取关联数据
    gt_result = await db.execute(
        select(BUltraResult).where(BUltraResult.patient_id == patient_id)
    )
    gt = gt_result.scalar_one_or_none()

    asr_result = await db.execute(
        select(PatientAsrResult).where(PatientAsrResult.patient_id == patient_id)
    )
    asr_map = {a.id: a for a in asr_result.scalars().all()}

    tmpl_result = await db.execute(select(PromptTemplate))
    tmpl_map = {t.id: t for t in tmpl_result.scalars().all()}

    wb = Workbook()
    ws = wb.active
    ws.title = "LLM历史"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1890FF", end_color="1890FF", fill_type="solid")
    header_wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    headers = [
        "LLM结果ID", "检查记录ID", "病历号", "检查日期", "执行时间", "状态", "准确率",
        "ASR结果ID", "ASR模型名称", "ASR转写来源", "LLM模型名称",
        "提示词模板ID", "提示词模板名称", "提示词长度",
        "提示词内容", "ASR原始转写", "实际送入LLM的ASR文本",
        "LLM_右侧卵泡总数", "LLM_右侧卵泡明细", "LLM_左侧卵泡总数", "LLM_左侧卵泡明细",
        "LLM_内膜厚度", "LLM_内膜类型",
        "LLM_右卵巢长", "LLM_右卵巢宽", "LLM_左卵巢长", "LLM_左卵巢宽",
        "LLM_备注", "LLM_总结", "LLM_不确定内容", "LLM_原始返回",
        "真实_右侧卵泡总数", "真实_右侧卵泡明细", "真实_左侧卵泡总数", "真实_左侧卵泡明细",
        "真实_内膜厚度", "真实_内膜类型",
        "真实_右卵巢长", "真实_右卵巢宽", "真实_左卵巢长", "真实_左卵巢宽",
        "真实_备注",
    ]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_wrap
        cell.border = thin_border

    def follicles_to_str(follicles):
        if not follicles or not isinstance(follicles, list):
            return "-"
        return "; ".join(f"{f.get('size', '?')}x{f.get('count', '?')}" for f in follicles)

    # 真实 B 超
    gt_right_total = gt.right_follicle_total if gt else ""
    gt_left_total = gt.left_follicle_total if gt else ""
    gt_endo_thick = gt.endometrium_thickness if gt else ""
    gt_endo_type = gt.endometrium_type if gt else ""
    gt_r_ovary_l = gt.right_ovary_length if gt else ""
    gt_r_ovary_w = gt.right_ovary_width if gt else ""
    gt_l_ovary_l = gt.left_ovary_length if gt else ""
    gt_l_ovary_w = gt.left_ovary_width if gt else ""
    gt_remark = gt.remark if gt else ""

    for row_idx, (llm, _patient, _df) in enumerate(rows, 2):
        structured = llm.structured_result or {}
        right_follicles = structured.get("right_follicles") or []
        left_follicles = structured.get("left_follicles") or []

        asr = asr_map.get(llm.asr_result_id) if llm.asr_result_id else None
        asr_model_name = asr.asr_model_name if asr else ""
        asr_transcript = asr.full_transcript if asr else ""

        tmpl_id = llm.prompt_template_id
        tmpl_name = llm.prompt_template_name or ""
        if not tmpl_name and tmpl_id and tmpl_id in tmpl_map:
            tmpl_name = tmpl_map[tmpl_id].name or ""

        row_data = [
            llm.id, patient_id, record_id, date_str,
            llm.created_at.strftime("%Y-%m-%d %H:%M:%S") if llm.created_at else "",
            llm.status, llm.accuracy,
            llm.asr_result_id, asr_model_name, "original", llm.llm_model_name,
            tmpl_id or "", tmpl_name or "未记录模板名称",
            len(llm.prompt_content) if llm.prompt_content else 0,
            llm.prompt_content or "", asr_transcript, asr_transcript,
            structured.get("right_follicle_total", ""), follicles_to_str(right_follicles),
            structured.get("left_follicle_total", ""), follicles_to_str(left_follicles),
            structured.get("endometrium_thickness", ""), structured.get("endometrium_type", ""),
            structured.get("right_ovary_length", ""), structured.get("right_ovary_width", ""),
            structured.get("left_ovary_length", ""), structured.get("left_ovary_width", ""),
            structured.get("remark", ""), llm.summary_text or "",
            structured.get("uncertain_text", ""), llm.raw_output or "",
            gt_right_total, follicles_to_str(gt.right_follicles if gt else []),
            gt_left_total, follicles_to_str(gt.left_follicles if gt else []),
            gt_endo_thick, gt_endo_type,
            gt_r_ovary_l, gt_r_ovary_w, gt_l_ovary_l, gt_l_ovary_w, gt_remark,
        ]
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.border = thin_border
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    col_widths = [
        10, 12, 12, 10, 18, 8, 8,
        10, 15, 12, 15, 12, 15, 10, 50, 50, 50,
        12, 25, 12, 25, 10, 10, 10, 10, 10, 10,
        30, 40, 30, 50,
        12, 25, 12, 25, 10, 10, 10, 10, 10, 10, 30,
    ]
    for idx, w in enumerate(col_widths, 1):
        col_letter = chr(64 + idx) if idx <= 26 else "A" + chr(64 + idx - 26)
        ws.column_dimensions[col_letter].width = w

    ws.freeze_panes = "A2"

    wb = Workbook()
    ws = wb.active
    ws.title = "LLM历史"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1890FF", end_color="1890FF", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    headers = [
        "检查记录ID", "病历号", "检查日期", "LLM结果ID", "执行时间",
        "ASR结果ID", "ASR模型", "LLM模型", "prompt_version", "prompt_len",
        "状态", "准确率", "summary_text",
        "right_follicle_total", "left_follicle_total",
        "right_follicles", "left_follicles",
        "endometrium_thickness", "endometrium_type",
        "right_ovary_length", "right_ovary_width",
        "left_ovary_length", "left_ovary_width",
        "remark", "uncertain_text", "raw_output",
    ]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    for row_idx, (llm, patient, date_folder) in enumerate(rows, 2):
        structured = llm.structured_result or {}
        right_follicles = structured.get("right_follicles") or []
        left_follicles = structured.get("left_follicles") or []
        row_data = [
            patient_id,
            record_id,
            date_str,
            llm.id,
            llm.created_at.strftime("%Y-%m-%d %H:%M:%S") if llm.created_at else "",
            llm.asr_result_id,
            "",
            llm.llm_model_name,
            llm.prompt_version,
            len(llm.prompt_content) if llm.prompt_content else 0,
            llm.status,
            llm.accuracy,
            llm.summary_text or "",
            structured.get("right_follicle_total", ""),
            structured.get("left_follicle_total", ""),
            json.dumps(right_follicles, ensure_ascii=False),
            json.dumps(left_follicles, ensure_ascii=False),
            structured.get("endometrium_thickness", ""),
            structured.get("endometrium_type", ""),
            structured.get("right_ovary_length", ""),
            structured.get("right_ovary_width", ""),
            structured.get("left_ovary_length", ""),
            structured.get("left_ovary_width", ""),
            structured.get("remark", ""),
            structured.get("uncertain_text", ""),
            llm.raw_output or "",
        ]
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.border = thin_border
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    col_widths = [12, 12, 12, 10, 18, 10, 15, 15, 12, 10, 8, 8, 40, 12, 12, 30, 30, 12, 12, 12, 12, 12, 12, 30, 30, 60]
    for idx, w in enumerate(col_widths, 1):
        col_letter = chr(64 + idx) if idx <= 26 else "A" + chr(64 + idx - 26)
        ws.column_dimensions[col_letter].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    # ASCII-only filename to avoid latin-1 encoding error
    safe_record = record_id.encode('ascii', 'ignore').decode()
    filename = f"LLM_history_{safe_record}_{date_str}.xlsx"

    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
