"""ASR 文本转化评估 API。"""
import json
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    AsrConversionBatch,
    AsrConversionDetail,
    AsrConversionMetric,
    AsrConversionRecord,
    AsrConversionReview,
    AsrReferenceTranscript,
    BUltraResult,
    PatientAsrResult,
    PatientRecord,
)
from app.models.conversion_config import ConversionConfigVersion, ConversionLexiconEntry
from app.schemas.conversion_eval import (
    ConversionBatchCreate,
    ConversionBatchCreateResult,
    ConversionBatchDetailOut,
    ConversionBatchOut,
    ConversionDetailCreate,
    ConversionDetailOut,
    ConversionDetailUpdate,
    ConversionMetricOut,
    ConversionRecordCreateFromExam,
    ConversionRecordDetailOut,
    ConversionRecordOut,
    ConversionRecordUpdate,
    ConversionReviewCreate,
    ConversionReviewOut,
)
from app.services.conversion_judge import apply_auto_judge
from app.services.conversion_engine.number_normalize import _normalize_multiply_operator
from app.services.conversion_metrics import calculate_conversion_metrics
from app.services.parser import compare_follicle_details, evaluate_result, normalize_follicles

router = APIRouter()

MANUAL_BUSINESS_RULE_ID = "manual_business_segment"
MANUAL_BUSINESS_NOTE_PREFIX = "__manual_business_segment__"
RULE_CANDIDATE_VERSION_CODE = "manual-candidates"


def _parse_manual_business_note(note: str | None) -> dict[str, Any]:
    text = note or ""
    if not text.startswith(MANUAL_BUSINESS_NOTE_PREFIX):
        return {"note": text}
    line_end = text.find("\n")
    head = text if line_end < 0 else text[:line_end]
    body = "" if line_end < 0 else text[line_end + 1 :]
    try:
        meta = json.loads(head.replace(MANUAL_BUSINESS_NOTE_PREFIX, "", 1))
        if isinstance(meta, dict):
            return {**meta, "note": body}
    except Exception:
        pass
    return {"note": body or text}


def _candidate_status(details: list[AsrConversionDetail]) -> str:
    judgements = {item.final_judgement or item.manual_judgement or "pending" for item in details}
    if judgements and judgements <= {"approved"}:
        return "approved"
    if judgements and judgements <= {"ignored"}:
        return "ignored"
    return "pending"


_MIXED_OVARY_SIZE_REMARK_PATTERN = re.compile(
    r"(?P<size>[零一二三四五六七八九十幺\d]+(?:乘以?|叉|[xX*])[零一二三四五六七八九十幺\d]+)(?P<remark>五回声|无回声)"
)


def _candidate_recommendation(raw: str, standard: str, segment_type: str, field_code: str) -> dict[str, Any]:
    """给人工候选加审核建议。

    这里只做提示，不直接改变正式规则。典型场景：
    “五八乘以三八五回声”实际包含两个业务事实：
    - 卵巢大小：五八乘以三八 -> 58×38
    - 备注：五回声/无回声 -> 无回声
    这类候选如果整体入规则，后续会把尺寸和备注粘成一条错误规则。
    """
    raw_match = _MIXED_OVARY_SIZE_REMARK_PATTERN.search(raw)
    standard_match = _MIXED_OVARY_SIZE_REMARK_PATTERN.search(standard)
    if segment_type == "medical_data" and field_code == "remark" and raw_match and standard_match:
        raw_size = raw_match.group("size")
        raw_remark = raw_match.group("remark")
        standard_size = standard_match.group("size")
        standard_remark = standard_match.group("remark").replace("五回声", "无回声")
        normalized_size, _ = _normalize_multiply_operator(standard_size)
        return {
            "recommendation": "split_required",
            "recommendation_note": "该候选同时包含卵巢大小和全局备注，建议拆成两条候选后再审核。",
            "suggested_splits": [
                {
                    "raw_fragment": raw_size,
                    "standard_text": normalized_size,
                    "segment_type": "medical_data",
                    "field_code": "ovary_size",
                },
                {
                    "raw_fragment": raw_remark,
                    "standard_text": standard_remark,
                    "segment_type": "medical_data",
                    "field_code": "remark",
                },
            ],
        }
    return {
        "recommendation": "normal",
        "recommendation_note": "",
        "suggested_splits": [],
    }


def _manual_business_details(record: AsrConversionRecord) -> list[AsrConversionDetail]:
    return [detail for detail in (record.details or []) if detail.rule_id == MANUAL_BUSINESS_RULE_ID]


def _apply_manual_business_overrides(converted_text: str, manual_details: list[AsrConversionDetail]) -> str:
    """Apply user-reviewed business segment corrections to converted ASR text.

    Manual marks are the user's explicit corrections. They should survive a
    rerun and, when possible, be reflected in the right-side converted ASR.
    The conservative rule is string replacement by raw fragment; if the auto
    engine already produced the same converted value, no change is needed.
    """
    text = converted_text or ""
    for detail in sorted(manual_details, key=lambda item: (item.raw_start if item.raw_start is not None else 10**9)):
        raw = (detail.raw_fragment or "").strip()
        converted = (detail.converted_fragment or "").strip()
        if not raw or not converted or raw == converted:
            continue
        if converted in text and raw not in text:
            continue
        if raw in text:
            text = text.replace(raw, converted, 1)
    return text


def _follicle_list_from_values(values: list[Any]) -> list[dict[str, Any]]:
    return normalize_follicles([{"size": value, "count": 1} for value in values])


def _split_size(value: Any) -> tuple[float | None, float | None]:
    if not value:
        return None, None
    text = str(value).replace("x", "×").replace("X", "×").replace("*", "×")
    if "×" not in text:
        return None, None
    left, _, right = text.partition("×")
    try:
        return float(left), float(right)
    except (TypeError, ValueError):
        return None, None


def _normalize_endometrium_type(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text in {"A", "B", "C"}:
        return f"{text}型"
    return text


def _structured_from_business_segments(segments: list[dict[str, Any]]) -> dict[str, Any]:
    structured: dict[str, Any] = {
        "right_follicles": [],
        "left_follicles": [],
        "right_follicle_total": 0,
        "left_follicle_total": 0,
    }
    right_values: list[Any] = []
    left_values: list[Any] = []

    for item in segments:
        if item.get("segment_type") != "medical_data" or item.get("participates") is False:
            continue
        field = item.get("field_code")
        value = item.get("normalized")
        if field == "endometrium_thickness":
            structured[field] = value
        elif field == "endometrium_type":
            structured[field] = _normalize_endometrium_type(value)
        elif field == "right_ovary_size":
            length, width = _split_size(value)
            structured["right_ovary_length"] = length
            structured["right_ovary_width"] = width
            structured["right_ovary_size"] = value
        elif field == "left_ovary_size":
            length, width = _split_size(value)
            structured["left_ovary_length"] = length
            structured["left_ovary_width"] = width
            structured["left_ovary_size"] = value
        elif field == "right_follicles":
            right_values.append(value)
        elif field == "left_follicles":
            left_values.append(value)
        elif field == "remark":
            existing = str(structured.get("remark") or "").strip()
            text = str(value or "").strip()
            if text and text not in existing:
                structured["remark"] = "；".join([part for part in [existing, text] if part])

    structured["right_follicles"] = _follicle_list_from_values(right_values)
    structured["left_follicles"] = _follicle_list_from_values(left_values)
    structured["right_follicle_total"] = sum(int(item.get("count") or 0) for item in structured["right_follicles"])
    structured["left_follicle_total"] = sum(int(item.get("count") or 0) for item in structured["left_follicles"])
    return structured


def _ground_truth_dict(gt: BUltraResult | None) -> dict[str, Any] | None:
    if not gt:
        return None
    right_size = None
    if gt.right_ovary_length is not None and gt.right_ovary_width is not None:
        right_size = f"{gt.right_ovary_length:g}×{gt.right_ovary_width:g}"
    left_size = None
    if gt.left_ovary_length is not None and gt.left_ovary_width is not None:
        left_size = f"{gt.left_ovary_length:g}×{gt.left_ovary_width:g}"
    return {
        "right_follicles": normalize_follicles(gt.right_follicles or []),
        "left_follicles": normalize_follicles(gt.left_follicles or []),
        "right_follicle_total": gt.right_follicle_total or 0,
        "left_follicle_total": gt.left_follicle_total or 0,
        "endometrium_thickness": gt.endometrium_thickness,
        "endometrium_type": _normalize_endometrium_type(gt.endometrium_type),
        "right_ovary_length": gt.right_ovary_length,
        "right_ovary_width": gt.right_ovary_width,
        "right_ovary_size": right_size,
        "left_ovary_length": gt.left_ovary_length,
        "left_ovary_width": gt.left_ovary_width,
        "left_ovary_size": left_size,
        "remark": gt.remark,
    }


def _summarize_follicle_diff(follicle_diff: dict[str, Any]) -> dict[str, int]:
    """汇总单条记录右/左卵泡明细差异的计数（缺失/额外/数量差/疑似串边）。"""
    totals = {
        "missing_total": 0,
        "extra_total": 0,
        "count_mismatch_total": 0,
        "possible_side_swap_total": 0,
    }
    for side in ("right_follicles", "left_follicles"):
        diff = (follicle_diff or {}).get(side) or {}
        totals["missing_total"] += len(diff.get("missing") or [])
        totals["extra_total"] += len(diff.get("extra") or [])
        totals["count_mismatch_total"] += len(diff.get("count_mismatch") or [])
        totals["possible_side_swap_total"] += len(diff.get("possible_side_swaps") or [])
    return totals


def _build_business_structure_compare(
    record: AsrConversionRecord,
    gt: BUltraResult | None,
) -> dict[str, Any]:
    """从评估记录定位业务片段，聚合结构化字段并与真实 B 超结果比对。

    单条结构化对比接口与批次结构化汇总接口复用。返回字段：
    text_source / extracted / ground_truth / comparison / segments / follicle_diff
    """
    from app.services.conversion_engine.business_segment_locator import locate_business_segments

    text = record.converted_text or record.raw_text or ""
    segments = locate_business_segments(text)
    extracted = _structured_from_business_segments(segments)
    ground_truth = _ground_truth_dict(gt)
    if ground_truth:
        comparison = evaluate_result(extracted, ground_truth, include_remark=False)
    else:
        comparison = {
            "fields": {},
            "total_fields": 0,
            "correct_fields": 0,
            "accuracy": 0.0,
            "include_remark": False,
        }

    follicle_diff = {
        "right_follicles": compare_follicle_details(
            extracted.get("right_follicles"),
            ground_truth.get("right_follicles") if ground_truth else None,
            extracted.get("left_follicles"),
        ),
        "left_follicles": compare_follicle_details(
            extracted.get("left_follicles"),
            ground_truth.get("left_follicles") if ground_truth else None,
            extracted.get("right_follicles"),
        ),
    }
    follicle_diff["summary"] = _summarize_follicle_diff(follicle_diff)

    return {
        "text_source": "converted" if record.converted_text else "raw",
        "extracted": extracted,
        "ground_truth": ground_truth,
        "comparison": comparison,
        "segments": segments,
        "follicle_diff": follicle_diff,
    }


async def _ensure_candidate_draft_version(db: AsyncSession) -> ConversionConfigVersion:
    version = (
        await db.execute(
            select(ConversionConfigVersion).where(ConversionConfigVersion.version_code == RULE_CANDIDATE_VERSION_CODE)
        )
    ).scalar_one_or_none()
    if version:
        return version
    version = ConversionConfigVersion(
        version_code=RULE_CANDIDATE_VERSION_CODE,
        version_name="人工候选规则草稿",
        status="draft",
        description="ASR 转化评估人工标记审核通过后自动进入的候选规则库，默认不启用。",
        created_by="system",
    )
    db.add(version)
    await db.flush()
    return version


async def _get_record_or_404(db: AsyncSession, record_id: int) -> AsrConversionRecord:
    result = await db.execute(
        select(AsrConversionRecord)
        .options(selectinload(AsrConversionRecord.details), selectinload(AsrConversionRecord.reviews))
        .where(AsrConversionRecord.id == record_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="转化评估记录不存在")
    return record


def _record_out(record: AsrConversionRecord) -> ConversionRecordOut:
    return ConversionRecordOut.model_validate(record)


def _detail_out(detail: AsrConversionDetail) -> ConversionDetailOut:
    return ConversionDetailOut.model_validate(detail)


@router.post("/records/from-exam/{exam_record_id}", response_model=ConversionRecordOut)
async def create_record_from_exam(
    exam_record_id: int,
    data: ConversionRecordCreateFromExam,
    db: AsyncSession = Depends(get_db),
):
    exam = (
        await db.execute(
            select(PatientRecord)
            .options(selectinload(PatientRecord.date_folder))
            .where(PatientRecord.id == exam_record_id)
        )
    ).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="检查记录不存在")

    asr_result = None
    if data.asr_result_id:
        asr_result = await db.get(PatientAsrResult, data.asr_result_id)
        if not asr_result or asr_result.patient_id != exam_record_id:
            raise HTTPException(status_code=400, detail="ASR结果不属于当前检查记录")
    else:
        result = await db.execute(
            select(PatientAsrResult)
            .where(PatientAsrResult.patient_id == exam_record_id, PatientAsrResult.status == "success")
            .order_by(PatientAsrResult.created_at.desc(), PatientAsrResult.id.desc())
        )
        asr_result = result.scalar_one_or_none()

    reference = (
        await db.execute(
            select(AsrReferenceTranscript)
            .where(AsrReferenceTranscript.patient_id == exam_record_id, AsrReferenceTranscript.is_current == True)
            .order_by(AsrReferenceTranscript.updated_at.desc(), AsrReferenceTranscript.id.desc())
        )
    ).scalar_one_or_none()

    raw_text = asr_result.full_transcript if asr_result else ""
    record = AsrConversionRecord(
        exam_record_id=exam.id,
        asr_result_id=asr_result.id if asr_result else None,
        reference_asr_id=reference.id if reference else None,
        record_id_snapshot=exam.record_id,
        date_snapshot=exam.date_folder.date if exam.date_folder else (asr_result.date if asr_result else None),
        asr_model_name=asr_result.asr_model_name if asr_result else None,
        source_config_hash=asr_result.config_hash if asr_result else None,
        raw_text=raw_text,
        converted_text=data.converted_text if data.converted_text is not None else raw_text,
        reference_text=reference.reference_text if reference else "",
        conversion_version=data.conversion_version or "manual",
        review_status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _record_out(record)


@router.post("/records/batch-from-exams")
async def batch_create_records_from_exams(
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    ids = [int(item) for item in body.get("exam_record_ids", []) if str(item).strip()]
    conversion_version = body.get("conversion_version") or "manual"
    if not ids:
        return {"created": [], "skipped": [], "failed": [], "created_count": 0, "skipped_count": 0, "failed_count": 0}

    created_list = []
    skipped_list = []
    failed_list = []

    for exam_id in ids:
        try:
            # 检查检查记录是否存在
            exam = (
                await db.execute(
                    select(PatientRecord)
                    .options(selectinload(PatientRecord.date_folder))
                    .where(PatientRecord.id == exam_id)
                )
            ).scalar_one_or_none()
            if not exam:
                failed_list.append({"exam_record_id": exam_id, "reason": "检查记录不存在"})
                continue

            # 查找最新成功 ASR
            asr_result = (
                await db.execute(
                    select(PatientAsrResult)
                    .where(PatientAsrResult.patient_id == exam_id, PatientAsrResult.status == "success")
                    .order_by(PatientAsrResult.created_at.desc(), PatientAsrResult.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not asr_result:
                skipped_list.append({"exam_record_id": exam_id, "record_id": exam.record_id, "reason": "无成功 ASR"})
                continue

            # 检查是否已存在相同配置的评估记录
            existing = (
                await db.execute(
                    select(AsrConversionRecord)
                    .where(
                        AsrConversionRecord.exam_record_id == exam_id,
                        AsrConversionRecord.asr_result_id == asr_result.id,
                        AsrConversionRecord.conversion_version == conversion_version,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing:
                skipped_list.append({
                    "exam_record_id": exam_id,
                    "record_id": exam.record_id,
                    "reason": "已存在相同评估记录",
                    "existing_record_id": existing.id,
                })
                continue

            # 查找人工标准 ASR
            reference = (
                await db.execute(
                    select(AsrReferenceTranscript)
                    .where(AsrReferenceTranscript.patient_id == exam_id, AsrReferenceTranscript.is_current == True)
                    .order_by(AsrReferenceTranscript.updated_at.desc(), AsrReferenceTranscript.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            # 创建评估记录
            raw_text = asr_result.full_transcript or ""
            record = AsrConversionRecord(
                exam_record_id=exam.id,
                asr_result_id=asr_result.id,
                reference_asr_id=reference.id if reference else None,
                record_id_snapshot=exam.record_id,
                date_snapshot=exam.date_folder.date if exam.date_folder else (asr_result.date if asr_result else None),
                asr_model_name=asr_result.asr_model_name if asr_result else None,
                source_config_hash=asr_result.config_hash if asr_result else None,
                raw_text=raw_text,
                converted_text=raw_text,  # 先设置为原始文本，后续运行转化引擎
                reference_text=reference.reference_text if reference else "",
                conversion_version=conversion_version,
                review_status="pending",
            )
            db.add(record)
            await db.flush()

            # 运行转化引擎
            try:
                from app.services.conversion_engine import run_conversion as run_engine
                conv_result = run_engine(
                    raw_text=raw_text,
                    scene="",
                    conversion_version=conversion_version,
                )

                # 更新转化文本和风险信息
                record.converted_text = conv_result.normalized_text
                record.warnings = "\n".join(conv_result.warnings) if conv_result.warnings else None
                record.risk_passed = 1 if conv_result.risk_passed else 0
                record.risk_blocked = 1 if conv_result.risk_blocked else 0
                record.fields_snapshot = conv_result.fields if conv_result.fields else None

                # 保存转化片段
                for conv in conv_result.conversions:
                    raw_start = conv.get("start", 0)
                    raw_end = conv.get("end", 0)

                    detail = AsrConversionDetail(
                        record_id=record.id,
                        raw_fragment=conv.get("raw", ""),
                        converted_fragment=conv.get("converted", ""),
                        raw_start=raw_start,
                        raw_end=raw_end,
                        action_type=conv.get("action", "replace").lower(),
                        category=conv.get("category", "other"),
                        rule_id=conv.get("rule_id"),
                        rule_version=conversion_version,
                        confidence=conv.get("confidence"),
                        risk_level=conv.get("risk_level", "low"),
                        risk_type=conv.get("risk_type"),
                        system_judgement="pending",
                        final_judgement="pending",
                        note=conv.get("notes"),
                    )
                    db.add(detail)
            except Exception:
                # 转化引擎失败不影响记录创建
                pass

            created_list.append({
                "exam_record_id": exam_id,
                "record_id": exam.record_id,
                "conversion_record_id": record.id,
            })
        except Exception as e:
            failed_list.append({"exam_record_id": exam_id, "reason": str(e)})

    await db.commit()
    return {
        "created": created_list,
        "skipped": skipped_list,
        "failed": failed_list,
        "created_count": len(created_list),
        "skipped_count": len(skipped_list),
        "failed_count": len(failed_list),
    }


# ========== 批次 ==========

async def _get_batch_or_404(db: AsyncSession, batch_id: int) -> AsrConversionBatch:
    batch = await db.get(AsrConversionBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    return batch


async def _select_asr_for_exam(
    db: AsyncSession,
    exam_id: int,
    asr_source_type: str,
    asr_config_hash: str | None,
) -> PatientAsrResult | None:
    """按批次 ASR 来源选择检查记录对应的 ASR 结果。"""
    stmt = select(PatientAsrResult).where(
        PatientAsrResult.patient_id == exam_id,
        PatientAsrResult.status == "success",
        PatientAsrResult.full_transcript.isnot(None),
        PatientAsrResult.full_transcript != "",
    )
    if asr_source_type == "config_hash" and asr_config_hash:
        stmt = stmt.where(PatientAsrResult.config_hash == asr_config_hash)
    stmt = stmt.order_by(PatientAsrResult.created_at.desc(), PatientAsrResult.id.desc()).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _create_record_in_batch(
    db: AsyncSession,
    batch: AsrConversionBatch,
    exam: PatientRecord,
    asr_result: PatientAsrResult,
    conversion_version: str,
) -> AsrConversionRecord:
    """在批次中创建一条评估记录（best-effort 运行转化引擎）。"""
    reference = (
        await db.execute(
            select(AsrReferenceTranscript)
            .where(AsrReferenceTranscript.patient_id == exam.id, AsrReferenceTranscript.is_current == True)
            .order_by(AsrReferenceTranscript.updated_at.desc(), AsrReferenceTranscript.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    raw_text = asr_result.full_transcript or ""
    record = AsrConversionRecord(
        batch_id=batch.id,
        exam_record_id=exam.id,
        asr_result_id=asr_result.id,
        reference_asr_id=reference.id if reference else None,
        record_id_snapshot=exam.record_id,
        date_snapshot=exam.date_folder.date if exam.date_folder else asr_result.date,
        asr_model_name=asr_result.asr_model_name,
        source_config_hash=asr_result.config_hash,
        raw_text=raw_text,
        converted_text=raw_text,  # 默认等于原始文本，转化引擎成功后被覆盖
        reference_text=reference.reference_text if reference else "",
        conversion_version=conversion_version or "manual",
        status="ready",
        review_status="pending",
    )
    db.add(record)
    await db.flush()

    try:
        from app.services.conversion_engine import run_conversion as run_engine
        conv_result = run_engine(raw_text=raw_text, scene="", conversion_version=record.conversion_version)
        record.converted_text = conv_result.normalized_text
        record.warnings = "\n".join(conv_result.warnings) if conv_result.warnings else None
        record.risk_passed = 1 if conv_result.risk_passed else 0
        record.risk_blocked = 1 if conv_result.risk_blocked else 0
        record.fields_snapshot = conv_result.fields if conv_result.fields else None
        for conv in conv_result.conversions:
            db.add(AsrConversionDetail(
                record_id=record.id,
                raw_fragment=conv.get("raw", ""),
                converted_fragment=conv.get("converted", ""),
                raw_start=conv.get("start", 0),
                raw_end=conv.get("end", 0),
                action_type=conv.get("action", "replace").lower(),
                category=conv.get("category", "other"),
                rule_id=conv.get("rule_id"),
                rule_version=record.conversion_version,
                confidence=conv.get("confidence"),
                risk_level=conv.get("risk_level", "low"),
                risk_type=conv.get("risk_type"),
                system_judgement="pending",
                final_judgement="pending",
                note=conv.get("notes"),
            ))
    except Exception as exc:
        # 转化引擎失败不影响记录创建，但写入 warnings 便于前端感知
        record.warnings = (record.warnings + "\n" if record.warnings else "") + f"转化引擎执行失败但记录已创建: {exc}"

    return record


async def _create_failed_record_in_batch(
    db: AsyncSession,
    batch: AsrConversionBatch,
    exam: PatientRecord,
    reason: str,
) -> AsrConversionRecord:
    """保留缺少 ASR 的检查记录，让批次详情能明确显示失败原因。"""
    reference = (
        await db.execute(
            select(AsrReferenceTranscript)
            .where(AsrReferenceTranscript.patient_id == exam.id, AsrReferenceTranscript.is_current == True)
            .order_by(AsrReferenceTranscript.updated_at.desc(), AsrReferenceTranscript.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    record = AsrConversionRecord(
        batch_id=batch.id,
        exam_record_id=exam.id,
        asr_result_id=None,
        reference_asr_id=reference.id if reference else None,
        record_id_snapshot=exam.record_id,
        date_snapshot=exam.date_folder.date if exam.date_folder else None,
        raw_text="",
        converted_text="",
        reference_text=reference.reference_text if reference else "",
        conversion_version=batch.conversion_version or "manual",
        status="failed",
        error_message=reason,
        warnings=reason,
        review_status="pending",
    )
    db.add(record)
    await db.flush()
    return record


@router.post("/batches", response_model=ConversionBatchCreateResult)
async def create_batch(data: ConversionBatchCreate, db: AsyncSession = Depends(get_db)):
    batch = AsrConversionBatch(
        name=data.name,
        date_scope=",".join(data.selected_dates or []),
        selected_dates=list(data.selected_dates or []),
        asr_source_type=data.asr_source_type or "latest_success",
        asr_config_hash=data.asr_config_hash,
        conversion_version=data.conversion_version or "manual",
        status="active",
    )
    db.add(batch)
    await db.flush()

    created_list: list[dict[str, Any]] = []
    skipped_list: list[dict[str, Any]] = []
    failed_list: list[dict[str, Any]] = []

    for exam_id in data.exam_record_ids:
        try:
            exam = (
                await db.execute(
                    select(PatientRecord)
                    .options(selectinload(PatientRecord.date_folder))
                    .where(PatientRecord.id == exam_id)
                )
            ).scalar_one_or_none()
            if not exam:
                failed_list.append({"exam_record_id": exam_id, "reason": "检查记录不存在"})
                continue

            asr_result = await _select_asr_for_exam(db, exam_id, batch.asr_source_type, batch.asr_config_hash)
            if not asr_result:
                failed_record = await _create_failed_record_in_batch(db, batch, exam, "无成功ASR")
                failed_list.append({
                    "exam_record_id": exam_id,
                    "record_id": exam.record_id,
                    "conversion_record_id": failed_record.id,
                    "reason": "无成功ASR",
                })
                continue

            existing = (
                await db.execute(
                    select(AsrConversionRecord)
                    .where(
                        AsrConversionRecord.batch_id == batch.id,
                        AsrConversionRecord.exam_record_id == exam_id,
                        AsrConversionRecord.asr_result_id == asr_result.id,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing:
                skipped_list.append({
                    "exam_record_id": exam_id,
                    "record_id": exam.record_id,
                    "reason": "已存在相同评估记录",
                    "existing_record_id": existing.id,
                })
                continue

            record = await _create_record_in_batch(db, batch, exam, asr_result, batch.conversion_version)
            created_list.append({
                "exam_record_id": exam_id,
                "record_id": exam.record_id,
                "conversion_record_id": record.id,
            })
        except Exception as e:
            failed_list.append({"exam_record_id": exam_id, "reason": str(e)})

    batch.record_count = len(created_list) + len(failed_list)
    batch.success_count = len(created_list)
    batch.failed_count = len(failed_list)
    await db.commit()
    await db.refresh(batch)
    return ConversionBatchCreateResult(
        batch=ConversionBatchOut.model_validate(batch),
        created=created_list,
        skipped=skipped_list,
        failed=failed_list,
        created_count=len(created_list),
        skipped_count=len(skipped_list),
        failed_count=len(failed_list),
    )


@router.get("/batches", response_model=list[ConversionBatchOut])
async def list_batches(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(AsrConversionBatch).order_by(AsrConversionBatch.created_at.desc(), AsrConversionBatch.id.desc())
        )
    ).scalars().all()
    return [ConversionBatchOut.model_validate(row) for row in rows]


@router.get("/batches/{batch_id}", response_model=ConversionBatchDetailOut)
async def get_batch(batch_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AsrConversionBatch)
        .options(selectinload(AsrConversionBatch.records))
        .where(AsrConversionBatch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    out = ConversionBatchDetailOut.model_validate(batch)
    out.records = [
        ConversionRecordOut.model_validate(r)
        for r in sorted(batch.records, key=lambda r: ((r.date_snapshot or ""), (r.record_id_snapshot or "")))
    ]
    return out


@router.get("/batches/{batch_id}/structure-summary")
async def get_batch_structure_summary(batch_id: int, db: AsyncSession = Depends(get_db)):
    """批次结构化对比汇总：右/左卵泡明细匹配统计与差异计数，附每条记录摘要。

    - status="failed" 的记录计入 failed_record_count，跳过对比；
    - 无 ground truth 的记录计入 missing_ground_truth_count，跳过对比；
    - 无 ASR 文本（raw/converted 均为空）计入 no_text_count，跳过对比；
    - 其余记录实时定位业务片段并计算卵泡明细差异。
    """
    await _get_batch_or_404(db, batch_id)
    records = (
        await db.execute(
            select(AsrConversionRecord)
            .where(AsrConversionRecord.batch_id == batch_id)
            .order_by(AsrConversionRecord.date_snapshot, AsrConversionRecord.record_id_snapshot)
        )
    ).scalars().all()

    exam_ids = [record.exam_record_id for record in records if record.exam_record_id]
    gt_by_exam: dict[int, BUltraResult] = {}
    if exam_ids:
        gt_rows = (
            await db.execute(select(BUltraResult).where(BUltraResult.patient_id.in_(exam_ids)))
        ).scalars().all()
        gt_by_exam = {gt.patient_id: gt for gt in gt_rows}

    field_summary = {
        "right_follicles": {"match": 0, "mismatch": 0},
        "left_follicles": {"match": 0, "mismatch": 0},
    }
    follicle_summary = {
        "missing_total": 0,
        "extra_total": 0,
        "count_mismatch_total": 0,
        "possible_side_swap_total": 0,
    }
    record_items: list[dict[str, Any]] = []
    compared_count = 0
    missing_ground_truth_count = 0
    failed_record_count = 0
    no_text_count = 0

    for record in records:
        base = {
            "record_id": record.id,
            "exam_record_id": record.exam_record_id,
            "record_id_snapshot": record.record_id_snapshot,
            "date_snapshot": record.date_snapshot,
            "status": "compared",
            "has_ground_truth": record.exam_record_id in gt_by_exam,
            "right_match": None,
            "left_match": None,
            "right_side_swap": False,
            "left_side_swap": False,
            "diff_summary": "",
        }
        if record.status == "failed":
            base["status"] = "failed"
            failed_record_count += 1
            record_items.append(base)
            continue
        gt = gt_by_exam.get(record.exam_record_id)
        if not gt:
            base["status"] = "no_ground_truth"
            missing_ground_truth_count += 1
            record_items.append(base)
            continue
        if not (record.raw_text or "").strip() and not (record.converted_text or "").strip():
            base["status"] = "no_text"
            no_text_count += 1
            record_items.append(base)
            continue

        built = _build_business_structure_compare(record, gt)
        follicle_diff = built["follicle_diff"]
        right_diff = follicle_diff.get("right_follicles") or {}
        left_diff = follicle_diff.get("left_follicles") or {}
        right_match = bool(right_diff.get("match"))
        left_match = bool(left_diff.get("match"))
        right_swap = bool(right_diff.get("possible_side_swaps"))
        left_swap = bool(left_diff.get("possible_side_swaps"))

        field_summary["right_follicles"]["match" if right_match else "mismatch"] += 1
        field_summary["left_follicles"]["match" if left_match else "mismatch"] += 1
        summary_totals = _summarize_follicle_diff(follicle_diff)
        for key in follicle_summary:
            follicle_summary[key] += summary_totals[key]

        side_parts = []
        for side, side_label, side_diff, swap in (
            ("right_follicles", "右侧", right_diff, right_swap),
            ("left_follicles", "左侧", left_diff, left_swap),
        ):
            text = (side_diff.get("summary") or "").strip()
            if text:
                side_parts.append(f"{side_label}{text}")

        base.update({
            "status": "compared",
            "right_match": right_match,
            "left_match": left_match,
            "right_side_swap": right_swap,
            "left_side_swap": left_swap,
            "diff_summary": "；".join(side_parts),
        })
        compared_count += 1
        record_items.append(base)

    return {
        "batch_id": batch_id,
        "record_count": len(records),
        "compared_count": compared_count,
        "missing_ground_truth_count": missing_ground_truth_count,
        "failed_record_count": failed_record_count,
        "no_text_count": no_text_count,
        "field_summary": field_summary,
        "follicle_summary": follicle_summary,
        "records": record_items,
    }


@router.delete("/batches/{batch_id}")
async def delete_batch(batch_id: int, db: AsyncSession = Depends(get_db)):
    batch = await _get_batch_or_404(db, batch_id)
    record_ids = (
        await db.execute(select(AsrConversionRecord.id).where(AsrConversionRecord.batch_id == batch.id))
    ).scalars().all()
    if record_ids:
        # 明细/审校随 record 的 ORM 级联删除，指标需显式删除
        await db.execute(delete(AsrConversionMetric).where(AsrConversionMetric.record_id.in_(record_ids)))
        records = (
            await db.execute(select(AsrConversionRecord).where(AsrConversionRecord.id.in_(record_ids)))
        ).scalars().all()
        for record in records:
            await db.delete(record)
    await db.delete(batch)
    await db.commit()
    return {"message": "删除成功"}


@router.post("/batches/{batch_id}/auto-judge")
async def auto_judge_batch(batch_id: int, db: AsyncSession = Depends(get_db)):
    batch = await _get_batch_or_404(db, batch_id)
    records = (
        await db.execute(
            select(AsrConversionRecord)
            .options(selectinload(AsrConversionRecord.details))
            .where(AsrConversionRecord.batch_id == batch.id)
        )
    ).scalars().all()
    for record in records:
        apply_auto_judge(record)
    batch.reviewed_count = len([r for r in records if r.review_status in {"reviewed", "approved"}])
    await db.commit()
    return {"processed": len(records)}


@router.post("/batches/{batch_id}/calculate-metrics")
async def calculate_batch_metrics(batch_id: int, db: AsyncSession = Depends(get_db)):
    batch = await _get_batch_or_404(db, batch_id)
    records = (
        await db.execute(
            select(AsrConversionRecord)
            .options(selectinload(AsrConversionRecord.details))
            .where(AsrConversionRecord.batch_id == batch.id)
        )
    ).scalars().all()
    accuracies: list[float] = []
    for record in records:
        metrics = calculate_conversion_metrics(record)
        record.metrics_summary = metrics
        await db.execute(delete(AsrConversionMetric).where(AsrConversionMetric.record_id == record.id))
        for metric_type, key in [
            ("accuracy", "conversion_accuracy"),
            ("error_rate", "error_rate"),
            ("missed_rate", "missed_rate"),
            ("over_conversion_rate", "over_conversion_rate"),
            ("candidate_hit_rate", "candidate_hit_rate"),
        ]:
            db.add(AsrConversionMetric(
                record_id=record.id,
                category="overall",
                metric_type=metric_type,
                numerator=0,
                denominator=0,
                value=float(metrics[key]),
            ))
        accuracies.append(float(metrics["conversion_accuracy"]))
    batch.record_count = len(records)
    batch.reviewed_count = len([r for r in records if r.review_status in {"reviewed", "approved"}])
    batch.average_accuracy = sum(accuracies) / len(accuracies) if accuracies else 0.0
    await db.commit()
    return {
        "batch_id": batch.id,
        "record_count": batch.record_count,
        "reviewed_count": batch.reviewed_count,
        "average_accuracy": batch.average_accuracy,
    }


@router.get("/records", response_model=list[ConversionRecordOut])
async def list_records(
    date: str | None = Query(None),
    record_id: str | None = Query(None),
    review_status: str | None = Query(None),
    conversion_version: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AsrConversionRecord).order_by(AsrConversionRecord.created_at.desc(), AsrConversionRecord.id.desc())
    if date:
        stmt = stmt.where(AsrConversionRecord.date_snapshot == date)
    if record_id:
        stmt = stmt.where(AsrConversionRecord.record_id_snapshot.contains(record_id))
    if review_status:
        stmt = stmt.where(AsrConversionRecord.review_status == review_status)
    if conversion_version:
        stmt = stmt.where(AsrConversionRecord.conversion_version == conversion_version)
    rows = (await db.execute(stmt)).scalars().all()
    return [_record_out(row) for row in rows]


async def _detail_out_with_annotations(db: AsyncSession, record: AsrConversionRecord) -> ConversionRecordDetailOut:
    """构造 ConversionRecordDetailOut 并补充 reference_annotations。"""
    out = ConversionRecordDetailOut.model_validate(record)
    if record.reference_asr_id:
        reference = await db.get(AsrReferenceTranscript, record.reference_asr_id)
        if reference and reference.reference_annotations:
            out.reference_annotations = list(reference.reference_annotations)
    return out


async def _sync_current_reference_snapshot(db: AsyncSession, record: AsrConversionRecord) -> bool:
    """同步检查记录当前专家标准 ASR 到转化评估记录快照。

    转化评估记录创建时会保存 reference_text 快照；但标准 ASR 可能在之后才补录或更新。
    详情页应展示当前标准 ASR，否则历史评估记录会一直空白。
    """
    reference = (
        await db.execute(
            select(AsrReferenceTranscript)
            .where(AsrReferenceTranscript.patient_id == record.exam_record_id, AsrReferenceTranscript.is_current == True)
            .order_by(AsrReferenceTranscript.updated_at.desc(), AsrReferenceTranscript.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not reference:
        return False
    changed = False
    if record.reference_asr_id != reference.id:
        record.reference_asr_id = reference.id
        changed = True
    if (record.reference_text or "") != (reference.reference_text or ""):
        record.reference_text = reference.reference_text or ""
        changed = True
    return changed


@router.get("/records/{record_id}", response_model=ConversionRecordDetailOut)
async def get_record(record_id: int, db: AsyncSession = Depends(get_db)):
    record = await _get_record_or_404(db, record_id)
    if await _sync_current_reference_snapshot(db, record):
        await db.commit()
        record = await _get_record_or_404(db, record_id)
    return await _detail_out_with_annotations(db, record)


@router.get("/records/{record_id}/business-segments")
async def get_record_business_segments(
    record_id: int,
    text_source: str = "raw",
    db: AsyncSession = Depends(get_db),
):
    """返回业务片段定位结果，不写入转化明细。"""
    from app.services.conversion_engine.business_segment_locator import locate_business_segments

    record = await _get_record_or_404(db, record_id)
    source_map = {
        "raw": record.raw_text or "",
        "converted": record.converted_text or "",
        "reference": record.reference_text or "",
    }
    if text_source not in source_map:
        raise HTTPException(status_code=400, detail="text_source 仅支持 raw/converted/reference")
    text = source_map[text_source]
    return {
        "record_id": record.id,
        "text_source": text_source,
        "text": text,
        "segments": locate_business_segments(text),
    }


@router.get("/records/{record_id}/business-structure-compare")
async def get_record_business_structure_compare(record_id: int, db: AsyncSession = Depends(get_db)):
    """按当前业务片段定位结果聚合结构化字段，并与真实 B 超结果比对。

    返回顶层 follicle_diff（右/左卵泡明细的尺寸级/数量级差异 + summary 计数），
    comparison.fields 保持原结构不变。
    """
    record = await _get_record_or_404(db, record_id)
    gt = (
        await db.execute(
            select(BUltraResult).where(BUltraResult.patient_id == record.exam_record_id)
        )
    ).scalar_one_or_none()
    built = _build_business_structure_compare(record, gt)

    return {
        "record_id": record.id,
        "exam_record_id": record.exam_record_id,
        "text_source": built["text_source"],
        "extracted": built["extracted"],
        "ground_truth": built["ground_truth"],
        "comparison": built["comparison"],
        "segments": built["segments"],
        "follicle_diff": built["follicle_diff"],
    }


@router.get("/rule-candidates")
async def list_rule_candidates(
    status: str | None = Query(None),
    segment_type: str | None = Query(None),
    field_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """按人工业务片段聚合规则优化候选。

    候选来源仍存放在 asr_conversion_details 中：
    - rule_id = manual_business_segment
    - note 头部保存 segment_type / field_code / participates / optimize_candidate 等元信息
    这里只聚合，不改变正式规则。
    """
    rows = (
        await db.execute(
            select(AsrConversionDetail, AsrConversionRecord)
            .join(AsrConversionRecord, AsrConversionDetail.record_id == AsrConversionRecord.id)
            .where(AsrConversionDetail.rule_id == MANUAL_BUSINESS_RULE_ID)
            .order_by(AsrConversionDetail.updated_at.desc(), AsrConversionDetail.id.desc())
        )
    ).all()

    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for detail, record in rows:
        meta = _parse_manual_business_note(detail.note)
        item_segment_type = str(meta.get("segment_type") or detail.risk_type or "")
        item_field_code = str(meta.get("field_code") or detail.category or "")
        participates = bool(meta.get("participates", True))
        optimize_candidate = bool(meta.get("optimize_candidate", participates))
        if not participates or not optimize_candidate:
            continue
        if segment_type and item_segment_type != segment_type:
            continue
        if field_code and item_field_code != field_code:
            continue

        raw = (detail.raw_fragment or "").strip()
        standard = (detail.converted_fragment or detail.raw_fragment or "").strip()
        if not raw or not standard:
            continue
        key = (raw, standard, item_segment_type, item_field_code)
        bucket = groups.setdefault(key, {
            "raw_fragment": raw,
            "standard_text": standard,
            "segment_type": item_segment_type,
            "field_code": item_field_code,
            "occurrence_count": 0,
            "detail_ids": [],
            "record_ids": [],
            "batch_ids": [],
            "examples": [],
            "_details": [],
        })
        bucket["occurrence_count"] += 1
        bucket["detail_ids"].append(detail.id)
        if record.record_id_snapshot and record.record_id_snapshot not in bucket["record_ids"]:
            bucket["record_ids"].append(record.record_id_snapshot)
        if record.batch_id and record.batch_id not in bucket["batch_ids"]:
            bucket["batch_ids"].append(record.batch_id)
        if len(bucket["examples"]) < 5:
            start = detail.raw_start if detail.raw_start is not None else 0
            end = detail.raw_end if detail.raw_end is not None else start + len(raw)
            bucket["examples"].append({
                "detail_id": detail.id,
                "conversion_record_id": record.id,
                "record_id": record.record_id_snapshot,
                "date": record.date_snapshot,
                "context_before": detail.context_before or "",
                "context_after": detail.context_after or "",
                "raw_start": start,
                "raw_end": end,
                "note": meta.get("note") or "",
                "reason": meta.get("reason") or "",
            })
        bucket["_details"].append(detail)
        bucket.update(_candidate_recommendation(raw, standard, item_segment_type, item_field_code))

    result = []
    for bucket in groups.values():
        bucket["status"] = _candidate_status(bucket.pop("_details"))
        if status and bucket["status"] != status:
            continue
        result.append(bucket)
    result.sort(key=lambda item: (-int(item["occurrence_count"]), item["raw_fragment"]))
    return result


@router.post("/rule-candidates/ignore")
async def ignore_rule_candidate(body: dict[str, Any], db: AsyncSession = Depends(get_db)):
    raw = str(body.get("raw_fragment") or "").strip()
    standard = str(body.get("standard_text") or body.get("converted_fragment") or "").strip()
    segment_type = str(body.get("segment_type") or "").strip()
    field_code = str(body.get("field_code") or "").strip()
    if not raw or not standard:
        raise HTTPException(status_code=400, detail="缺少候选原文或标准值")

    details = await _matching_manual_candidate_details(db, raw, standard, segment_type, field_code)
    for detail in details:
        detail.manual_judgement = "ignored"
        detail.final_judgement = "ignored"
    await db.commit()
    return {"updated_details": len(details), "status": "ignored"}


@router.post("/rule-candidates/approve")
async def approve_rule_candidate(body: dict[str, Any], db: AsyncSession = Depends(get_db)):
    raw = str(body.get("raw_fragment") or "").strip()
    standard = str(body.get("standard_text") or body.get("converted_fragment") or "").strip()
    segment_type = str(body.get("segment_type") or "").strip()
    field_code = str(body.get("field_code") or "").strip()
    note = str(body.get("note") or "").strip()
    if not raw or not standard:
        raise HTTPException(status_code=400, detail="缺少候选原文或标准值")

    details = await _matching_manual_candidate_details(db, raw, standard, segment_type, field_code)
    for detail in details:
        detail.manual_judgement = "approved"
        detail.final_judgement = "approved"

    version = await _ensure_candidate_draft_version(db)
    existing = (
        await db.execute(
            select(ConversionLexiconEntry).where(
                ConversionLexiconEntry.version_id == version.id,
                ConversionLexiconEntry.error_text == raw,
                ConversionLexiconEntry.standard_text == standard,
            )
        )
    ).scalar_one_or_none()
    if existing:
        lexicon = existing
    else:
        lexicon = ConversionLexiconEntry(
            version_id=version.id,
            rule_code=f"MC{int(datetime.utcnow().timestamp())}",
            error_text=raw,
            standard_text=standard,
            business_scene="通用",
            match_type="exact",
            action="AUTO",
            risk_level="medium",
            confidence=0.95,
            priority=100,
            enabled=0,
            notes="；".join([item for item in [
                "人工候选池审核通过，默认未启用",
                f"类型={segment_type}" if segment_type else "",
                f"字段={field_code}" if field_code else "",
                note,
            ] if item]),
        )
        db.add(lexicon)
        await db.flush()

    await db.commit()
    await db.refresh(lexicon)
    return {
        "updated_details": len(details),
        "status": "approved",
        "lexicon": {
            "id": lexicon.id,
            "version_id": lexicon.version_id,
            "version_code": version.version_code,
            "error_text": lexicon.error_text,
            "standard_text": lexicon.standard_text,
            "enabled": lexicon.enabled,
        },
    }


async def _matching_manual_candidate_details(
    db: AsyncSession,
    raw: str,
    standard: str,
    segment_type: str = "",
    field_code: str = "",
) -> list[AsrConversionDetail]:
    rows = (
        await db.execute(
            select(AsrConversionDetail)
            .where(
                AsrConversionDetail.rule_id == MANUAL_BUSINESS_RULE_ID,
                AsrConversionDetail.raw_fragment == raw,
                AsrConversionDetail.converted_fragment == standard,
            )
            .order_by(AsrConversionDetail.id.asc())
        )
    ).scalars().all()
    matched = []
    for detail in rows:
        meta = _parse_manual_business_note(detail.note)
        if segment_type and str(meta.get("segment_type") or detail.risk_type or "") != segment_type:
            continue
        if field_code and str(meta.get("field_code") or detail.category or "") != field_code:
            continue
        matched.append(detail)
    return matched


@router.put("/records/{record_id}", response_model=ConversionRecordOut)
async def update_record(record_id: int, data: ConversionRecordUpdate, db: AsyncSession = Depends(get_db)):
    record = await _get_record_or_404(db, record_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    await db.commit()
    await db.refresh(record)
    return _record_out(record)


@router.delete("/records/{record_id}")
async def delete_record(record_id: int, db: AsyncSession = Depends(get_db)):
    record = await _get_record_or_404(db, record_id)
    await db.delete(record)
    await db.commit()
    return {"message": "删除成功"}


@router.post("/records/{record_id}/run-conversion", response_model=ConversionRecordDetailOut)
async def run_conversion_on_record(record_id: int, db: AsyncSession = Depends(get_db)):
    """对评估记录运行转化引擎"""
    from app.services.conversion_engine import run_conversion as run_engine
    from app.services.conversion_config import load_enabled_lexicon_rules, load_version_by_selector

    record = await _get_record_or_404(db, record_id)
    manual_details = _manual_business_details(record)

    # 先清理旧的自动转化片段，避免重复追加；人工业务标记必须保留。
    await db.execute(
        delete(AsrConversionDetail).where(
            AsrConversionDetail.record_id == record.id,
            AsrConversionDetail.rule_id != MANUAL_BUSINESS_RULE_ID,
        )
    )

    config_version = await load_version_by_selector(db, version_code=record.conversion_version)
    extra_rules = await load_enabled_lexicon_rules(db, config_version.id) if config_version else []

    # 运行转化引擎
    result = run_engine(
        raw_text=record.raw_text,
        scene="",  # 自动推断
        conversion_version=config_version.version_code if config_version else record.conversion_version,
        extra_confusion_rules=extra_rules,
    )

    # 更新记录
    record.converted_text = _apply_manual_business_overrides(result.normalized_text, manual_details)
    record.warnings = "\n".join(result.warnings) if result.warnings else None
    record.risk_passed = 1 if result.risk_passed else 0
    record.risk_blocked = 1 if result.risk_blocked else 0
    record.fields_snapshot = result.fields if result.fields else None

    # 保存转化片段
    for conv in result.conversions:
        # 计算结束位置
        raw_start = conv.get("start", 0)
        raw_end = conv.get("end", 0)

        detail = AsrConversionDetail(
            record_id=record.id,
            raw_fragment=conv.get("raw", ""),
            converted_fragment=conv.get("converted", ""),
            raw_start=raw_start,
            raw_end=raw_end,
            action_type=conv.get("action", "replace").lower(),
            category=conv.get("category", "other"),
            rule_id=conv.get("rule_id"),
            rule_version=record.conversion_version,
            confidence=conv.get("confidence"),
            risk_level=conv.get("risk_level", "low"),
            risk_type=conv.get("risk_type"),
            system_judgement="pending",
            final_judgement="pending",
            note=conv.get("notes"),
        )
        db.add(detail)

    await db.commit()
    reloaded = await _get_record_or_404(db, record_id)
    return await _detail_out_with_annotations(db, reloaded)


@router.post("/records/batch-run-conversion")
async def batch_run_conversion(body: dict[str, Any], db: AsyncSession = Depends(get_db)):
    """批量运行转化引擎"""
    from app.services.conversion_engine import run_conversion as run_engine
    from app.services.conversion_config import load_enabled_lexicon_rules, load_version_by_selector

    ids = [int(item) for item in body.get("record_ids", []) if str(item).strip()]
    if not ids:
        return {"processed": 0}

    processed = 0
    for record_id in ids:
        try:
            record = await _get_record_or_404(db, record_id)
            manual_details = _manual_business_details(record)

            # 先清理旧的自动转化片段，避免重复追加；人工业务标记必须保留。
            await db.execute(
                delete(AsrConversionDetail).where(
                    AsrConversionDetail.record_id == record.id,
                    AsrConversionDetail.rule_id != MANUAL_BUSINESS_RULE_ID,
                )
            )

            config_version = await load_version_by_selector(db, version_code=record.conversion_version)
            extra_rules = await load_enabled_lexicon_rules(db, config_version.id) if config_version else []

            # 运行转化引擎
            result = run_engine(
                raw_text=record.raw_text,
                scene="",
                conversion_version=config_version.version_code if config_version else record.conversion_version,
                extra_confusion_rules=extra_rules,
            )

            # 更新记录
            record.converted_text = _apply_manual_business_overrides(result.normalized_text, manual_details)
            record.warnings = "\n".join(result.warnings) if result.warnings else None
            record.risk_passed = 1 if result.risk_passed else 0
            record.risk_blocked = 1 if result.risk_blocked else 0
            record.fields_snapshot = result.fields if result.fields else None

            # 保存转化片段
            for conv in result.conversions:
                raw_start = conv.get("start", 0)
                raw_end = conv.get("end", 0)

                detail = AsrConversionDetail(
                    record_id=record.id,
                    raw_fragment=conv.get("raw", ""),
                    converted_fragment=conv.get("converted", ""),
                    raw_start=raw_start,
                    raw_end=raw_end,
                    action_type=conv.get("action", "replace").lower(),
                    category=conv.get("category", "other"),
                    rule_id=conv.get("rule_id"),
                    rule_version=record.conversion_version,
                    confidence=conv.get("confidence"),
                    risk_level=conv.get("risk_level", "low"),
                    risk_type=conv.get("risk_type"),
                    system_judgement="pending",
                    final_judgement="pending",
                    note=conv.get("notes"),
                )
                db.add(detail)

            processed += 1
        except Exception as e:
            # 单条失败不影响其他记录
            pass

    await db.commit()
    return {"processed": processed}


@router.post("/records/{record_id}/details", response_model=ConversionDetailOut)
async def create_detail(record_id: int, data: ConversionDetailCreate, db: AsyncSession = Depends(get_db)):
    record = await _get_record_or_404(db, record_id)
    detail = AsrConversionDetail(record_id=record.id, **data.model_dump())
    db.add(detail)
    await db.commit()
    await db.refresh(detail)
    return _detail_out(detail)


@router.post("/records/{record_id}/details/bulk", response_model=list[ConversionDetailOut])
async def bulk_create_details(record_id: int, data: list[ConversionDetailCreate], db: AsyncSession = Depends(get_db)):
    record = await _get_record_or_404(db, record_id)
    details = [AsrConversionDetail(record_id=record.id, **item.model_dump()) for item in data]
    db.add_all(details)
    await db.commit()
    for detail in details:
        await db.refresh(detail)
    return [_detail_out(detail) for detail in details]


@router.put("/details/{detail_id}", response_model=ConversionDetailOut)
async def update_detail(detail_id: int, data: ConversionDetailUpdate, db: AsyncSession = Depends(get_db)):
    detail = await db.get(AsrConversionDetail, detail_id)
    if not detail:
        raise HTTPException(status_code=404, detail="转化片段不存在")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(detail, key, value)
    if detail.manual_judgement:
        detail.final_judgement = detail.manual_judgement
    await db.commit()
    await db.refresh(detail)
    return _detail_out(detail)


@router.delete("/details/{detail_id}")
async def delete_detail(detail_id: int, db: AsyncSession = Depends(get_db)):
    detail = await db.get(AsrConversionDetail, detail_id)
    if not detail:
        raise HTTPException(status_code=404, detail="转化片段不存在")
    await db.delete(detail)
    await db.commit()
    return {"message": "删除成功"}


@router.post("/records/{record_id}/auto-judge", response_model=ConversionRecordDetailOut)
async def auto_judge_record(record_id: int, db: AsyncSession = Depends(get_db)):
    record = await _get_record_or_404(db, record_id)
    apply_auto_judge(record)
    await db.commit()
    return await _detail_out_with_annotations(db, await _get_record_or_404(db, record_id))


@router.post("/records/batch-auto-judge")
async def batch_auto_judge(body: dict[str, Any], db: AsyncSession = Depends(get_db)):
    ids = [int(item) for item in body.get("record_ids", []) if str(item).strip()]
    count = 0
    for record_id in ids:
        record = await _get_record_or_404(db, record_id)
        apply_auto_judge(record)
        count += 1
    await db.commit()
    return {"processed": count}


@router.post("/records/{record_id}/reviews", response_model=ConversionReviewOut)
async def create_review(record_id: int, data: ConversionReviewCreate, db: AsyncSession = Depends(get_db)):
    record = await _get_record_or_404(db, record_id)
    review = AsrConversionReview(record_id=record.id, **data.model_dump())
    db.add(review)
    if data.detail_id:
        detail = await db.get(AsrConversionDetail, data.detail_id)
        if detail and detail.record_id == record.id:
            detail.manual_judgement = data.review_action
            detail.final_judgement = data.review_action
            if data.is_high_risk:
                detail.risk_level = "high"
                detail.risk_type = data.high_risk_type or detail.risk_type
    await db.commit()
    await db.refresh(review)
    return ConversionReviewOut.model_validate(review)


@router.post("/records/{record_id}/calculate-metrics", response_model=ConversionMetricOut)
async def calculate_metrics(record_id: int, db: AsyncSession = Depends(get_db)):
    record = await _get_record_or_404(db, record_id)
    metrics = calculate_conversion_metrics(record)
    record.metrics_summary = metrics
    await db.execute(delete(AsrConversionMetric).where(AsrConversionMetric.record_id == record.id))
    for metric_type, key in [
        ("accuracy", "conversion_accuracy"),
        ("error_rate", "error_rate"),
        ("missed_rate", "missed_rate"),
        ("over_conversion_rate", "over_conversion_rate"),
        ("candidate_hit_rate", "candidate_hit_rate"),
    ]:
        db.add(AsrConversionMetric(
            record_id=record.id,
            category="overall",
            metric_type=metric_type,
            numerator=0,
            denominator=0,
            value=float(metrics[key]),
        ))
    await db.commit()
    return ConversionMetricOut(**metrics)


@router.post("/records/batch-calculate-metrics")
async def batch_calculate_metrics(body: dict[str, Any], db: AsyncSession = Depends(get_db)):
    ids = [int(item) for item in body.get("record_ids", []) if str(item).strip()]
    output = []
    for record_id in ids:
        record = await _get_record_or_404(db, record_id)
        metrics = calculate_conversion_metrics(record)
        record.metrics_summary = metrics
        output.append(metrics)
    await db.commit()
    return output


@router.get("/stats/overview")
async def stats_overview(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AsrConversionRecord))).scalars().all()
    total = len(rows)
    reviewed = len([row for row in rows if row.review_status in {"reviewed", "approved"}])
    avg_accuracy = 0.0
    accuracies = [float((row.metrics_summary or {}).get("conversion_accuracy", 0) or 0) for row in rows if row.metrics_summary]
    if accuracies:
        avg_accuracy = sum(accuracies) / len(accuracies)
    return {"total": total, "reviewed": reviewed, "pending": total - reviewed, "average_accuracy": avg_accuracy}


@router.get("/stats/by-category")
async def stats_by_category(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AsrConversionRecord))).scalars().all()
    aggregate: dict[str, dict[str, float]] = {}
    for row in rows:
        for category, stat in ((row.metrics_summary or {}).get("category_stats") or {}).items():
            target = aggregate.setdefault(category, {"actual": 0, "correct": 0, "wrong": 0, "missed": 0, "over": 0})
            target["actual"] += stat.get("actual_conversion_count", 0)
            target["correct"] += stat.get("correct_conversion_count", 0)
            target["wrong"] += stat.get("wrong_conversion_count", 0)
            target["missed"] += stat.get("missed_conversion_count", 0)
            target["over"] += stat.get("over_conversion_count", 0)
    for stat in aggregate.values():
        stat["accuracy"] = stat["correct"] / stat["actual"] if stat["actual"] else 0
    return aggregate


@router.get("/stats/high-risk")
async def stats_high_risk(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(AsrConversionDetail)
        .where(AsrConversionDetail.risk_level == "high")
        .order_by(AsrConversionDetail.updated_at.desc(), AsrConversionDetail.id.desc())
    )).scalars().all()
    return [_detail_out(row) for row in rows]
