"""ASR 文本转化评估 API。"""
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
    PatientAsrResult,
    PatientRecord,
)
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
from app.services.conversion_metrics import calculate_conversion_metrics

router = APIRouter()


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


@router.get("/records/{record_id}", response_model=ConversionRecordDetailOut)
async def get_record(record_id: int, db: AsyncSession = Depends(get_db)):
    record = await _get_record_or_404(db, record_id)
    return await _detail_out_with_annotations(db, record)


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

    record = await _get_record_or_404(db, record_id)

    # 先清理旧的转化片段，避免重复追加
    await db.execute(delete(AsrConversionDetail).where(AsrConversionDetail.record_id == record.id))

    # 运行转化引擎
    result = run_engine(
        raw_text=record.raw_text,
        scene="",  # 自动推断
        conversion_version=record.conversion_version,
    )

    # 更新记录
    record.converted_text = result.normalized_text
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

    ids = [int(item) for item in body.get("record_ids", []) if str(item).strip()]
    if not ids:
        return {"processed": 0}

    processed = 0
    for record_id in ids:
        try:
            record = await _get_record_or_404(db, record_id)

            # 先清理旧的转化片段，避免重复追加
            await db.execute(delete(AsrConversionDetail).where(AsrConversionDetail.record_id == record.id))

            # 运行转化引擎
            result = run_engine(
                raw_text=record.raw_text,
                scene="",
                conversion_version=record.conversion_version,
            )

            # 更新记录
            record.converted_text = result.normalized_text
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
