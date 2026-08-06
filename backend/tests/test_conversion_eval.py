"""Tests for ASR conversion evaluation P0 workflow."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import AsrConversionDetail, AsrReferenceTranscript, PatientAsrResult, PatientRecord
from app.models.conversion_config import ConversionLexiconEntry


@pytest.mark.anyio
async def test_create_conversion_record_from_exam_snapshots_existing_asr_and_reference(
    async_client: AsyncClient,
    db_session,
):
    patient = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A017750"))
    ).scalar_one()
    asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="豆包 ASR",
        provider="volcengine",
        config_hash="hash-a",
        full_transcript="内膜九点二，肉卵巢大小三九乘三零。",
        status="success",
    )
    db_session.add(asr)
    await db_session.flush()
    reference = AsrReferenceTranscript(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        base_asr_result_id=asr.id,
        reference_text="内膜9.2，右卵巢大小39×30。",
    )
    db_session.add(reference)
    await db_session.commit()

    response = await async_client.post(f"/conversion-eval/records/from-exam/{patient.id}", json={"asr_result_id": asr.id})

    assert response.status_code == 200
    data = response.json()
    assert data["exam_record_id"] == patient.id
    assert data["asr_result_id"] == asr.id
    assert data["reference_asr_id"] == reference.id
    assert data["raw_text"] == asr.full_transcript
    assert data["converted_text"] == asr.full_transcript
    assert data["reference_text"] == reference.reference_text
    assert data["source_config_hash"] == "hash-a"


@pytest.mark.anyio
async def test_auto_judge_and_metrics_classify_correct_wrong_missed_and_over_converted(
    async_client: AsyncClient,
    db_session,
):
    patient = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A017750"))
    ).scalar_one()
    asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="Test ASR",
        provider="local",
        full_transcript="肉卵巢 9.2 尾生欠军 右卵巢",
        status="success",
    )
    ref = AsrReferenceTranscript(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        reference_text="右卵巢 9.2 回声欠均 右卵巢",
    )
    db_session.add_all([asr, ref])
    await db_session.commit()
    record = (await async_client.post(f"/conversion-eval/records/from-exam/{patient.id}", json={"asr_result_id": asr.id})).json()

    detail_payloads = [
        {"raw_fragment": "肉卵巢", "converted_fragment": "右卵巢", "raw_start": 0, "raw_end": 3, "category": "medical_term", "action_type": "replace", "rule_id": "R001", "rule_version": "V1"},
        {"raw_fragment": "9.2", "converted_fragment": "5.2", "raw_start": 4, "raw_end": 7, "category": "number_format", "action_type": "replace", "rule_id": "R002", "rule_version": "V1", "risk_type": "number_error"},
        {"raw_fragment": "尾生欠军", "converted_fragment": "尾生欠军", "raw_start": 8, "raw_end": 12, "category": "medical_term", "action_type": "no_change", "rule_id": "R003", "rule_version": "V1"},
        {"raw_fragment": "右卵巢", "converted_fragment": "左卵巢", "raw_start": 13, "raw_end": 16, "category": "left_right", "action_type": "replace", "rule_id": "R004", "rule_version": "V1", "risk_type": "left_right"},
    ]
    for payload in detail_payloads:
        response = await async_client.post(f"/conversion-eval/records/{record['id']}/details", json=payload)
        assert response.status_code == 200

    judged = await async_client.post(f"/conversion-eval/records/{record['id']}/auto-judge")
    assert judged.status_code == 200
    results = [item["system_judgement"] for item in judged.json()["details"]]
    assert results == ["correct", "wrong", "missed", "over_converted"]

    metrics = await async_client.post(f"/conversion-eval/records/{record['id']}/calculate-metrics")
    assert metrics.status_code == 200
    metric = metrics.json()
    assert metric["actual_conversion_count"] == 3
    assert metric["correct_conversion_count"] == 1
    assert metric["wrong_conversion_count"] == 1
    assert metric["missed_conversion_count"] == 1
    assert metric["over_conversion_count"] == 1
    assert metric["high_risk_error_count"] == 2
    assert metric["conversion_accuracy"] == pytest.approx(1 / 3)


# ========== 批次评估工作台 ==========

from datetime import datetime, timedelta

from app.models import AsrConversionBatch, AsrConversionRecord


def _make_asr(patient, config_hash, transcript, created_at, status="success"):
    return PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="Test ASR",
        provider="local",
        config_hash=config_hash,
        full_transcript=transcript,
        status=status,
        created_at=created_at,
    )


async def _get_patients(db_session):
    p1 = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A017750"))
    ).scalar_one()
    p2 = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A000000"))
    ).scalar_one()
    return p1, p2


@pytest.mark.anyio
async def test_create_batch_latest_success_picks_newest_success_asr(async_client: AsyncClient, db_session):
    p1, p2 = await _get_patients(db_session)
    base = datetime(2026, 6, 23, 10, 0, 0)
    # p1: 旧的成功 + 更新的成功，应选最新
    db_session.add_all([
        _make_asr(p1, "hash-old", "旧文本", base),
        _make_asr(p1, "hash-new", "新文本", base + timedelta(hours=1)),
    ])
    # p2: 只有一条成功 ASR
    db_session.add(_make_asr(p2, "hash-p2", "p2文本", base))
    await db_session.commit()

    response = await async_client.post("/conversion-eval/batches", json={
        "name": "测试批次 latest_success",
        "selected_dates": ["20260623"],
        "exam_record_ids": [p1.id, p2.id],
        "asr_source_type": "latest_success",
        "conversion_version": "V1",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["created_count"] == 2
    assert data["failed_count"] == 0
    assert data["batch"]["record_count"] == 2
    assert data["batch"]["asr_source_type"] == "latest_success"
    batch_id = data["batch"]["id"]

    records = (
        await db_session.execute(
            select(AsrConversionRecord).where(AsrConversionRecord.batch_id == batch_id)
        )
    ).scalars().all()
    assert len(records) == 2
    by_exam = {r.exam_record_id: r for r in records}
    assert by_exam[p1.id].source_config_hash == "hash-new"
    assert by_exam[p1.id].raw_text == "新文本"
    assert by_exam[p2.id].source_config_hash == "hash-p2"
    assert all(r.batch_id == batch_id for r in records)


@pytest.mark.anyio
async def test_create_batch_config_hash_selects_matching_asr(async_client: AsyncClient, db_session):
    p1, _ = await _get_patients(db_session)
    base = datetime(2026, 6, 23, 10, 0, 0)
    # 更新的成功 ASR 是指定指纹之外的，应仍选指定指纹（即使更旧）
    db_session.add_all([
        _make_asr(p1, "hash-target", "目标文本", base),
        _make_asr(p1, "hash-other", "其他文本", base + timedelta(hours=1)),
    ])
    await db_session.commit()

    response = await async_client.post("/conversion-eval/batches", json={
        "name": "测试批次 config_hash",
        "selected_dates": ["20260623"],
        "exam_record_ids": [p1.id],
        "asr_source_type": "config_hash",
        "asr_config_hash": "hash-target",
        "conversion_version": "V1",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["created_count"] == 1
    record = (
        await db_session.execute(
            select(AsrConversionRecord).where(AsrConversionRecord.batch_id == data["batch"]["id"])
        )
    ).scalar_one()
    assert record.source_config_hash == "hash-target"
    assert record.raw_text == "目标文本"


@pytest.mark.anyio
async def test_create_batch_exam_without_asr_goes_failed(async_client: AsyncClient, db_session):
    _, p2 = await _get_patients(db_session)  # p2 无任何 ASR

    response = await async_client.post("/conversion-eval/batches", json={
        "name": "无ASR批次",
        "selected_dates": ["20260623"],
        "exam_record_ids": [p2.id],
        "asr_source_type": "latest_success",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["created_count"] == 0
    assert data["failed_count"] == 1
    assert data["failed"][0]["exam_record_id"] == p2.id
    assert "无成功ASR" in data["failed"][0]["reason"]
    assert data["batch"]["record_count"] == 1
    assert data["batch"]["success_count"] == 0
    assert data["batch"]["failed_count"] == 1

    record = (
        await db_session.execute(
            select(AsrConversionRecord).where(
                AsrConversionRecord.batch_id == data["batch"]["id"],
                AsrConversionRecord.exam_record_id == p2.id,
            )
        )
    ).scalar_one()
    assert record.status == "failed"
    assert record.error_message == "无成功ASR"
    assert record.asr_result_id is None


@pytest.mark.anyio
async def test_create_batch_duplicate_exam_goes_skipped(async_client: AsyncClient, db_session):
    p1, _ = await _get_patients(db_session)
    db_session.add(_make_asr(p1, "hash-a", "文本", datetime(2026, 6, 23, 10, 0, 0)))
    await db_session.commit()

    # 同一请求内重复传入同一检查记录：第一条创建，第二条应 skipped
    response = await async_client.post("/conversion-eval/batches", json={
        "name": "重复批次",
        "selected_dates": ["20260623"],
        "exam_record_ids": [p1.id, p1.id],
        "asr_source_type": "latest_success",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["created_count"] == 1
    assert data["skipped_count"] == 1
    assert data["skipped"][0]["exam_record_id"] == p1.id


@pytest.mark.anyio
async def test_batch_calculate_metrics_updates_average_accuracy(async_client: AsyncClient, db_session):
    p1, _ = await _get_patients(db_session)
    db_session.add(_make_asr(p1, "hash-a", "肉卵巢", datetime(2026, 6, 23, 10, 0, 0)))
    ref = AsrReferenceTranscript(
        patient_id=p1.id,
        record_id=p1.record_id,
        date="20260623",
        reference_text="右卵巢",
    )
    db_session.add(ref)
    await db_session.commit()

    created = (await async_client.post("/conversion-eval/batches", json={
        "name": "指标批次",
        "selected_dates": ["20260623"],
        "exam_record_ids": [p1.id],
        "asr_source_type": "latest_success",
    })).json()
    batch_id = created["batch"]["id"]
    record_id = created["created"][0]["conversion_record_id"]

    await async_client.post(f"/conversion-eval/records/{record_id}/details", json={
        "raw_fragment": "肉卵巢",
        "converted_fragment": "右卵巢",
        "raw_start": 0,
        "raw_end": 3,
        "category": "medical_term",
        "action_type": "replace",
    })
    judged = await async_client.post(f"/conversion-eval/batches/{batch_id}/auto-judge")
    assert judged.status_code == 200
    assert judged.json()["processed"] == 1

    response = await async_client.post(f"/conversion-eval/batches/{batch_id}/calculate-metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["record_count"] == 1
    assert data["average_accuracy"] == pytest.approx(1.0)

    batch = await db_session.get(AsrConversionBatch, batch_id)
    assert batch.average_accuracy == pytest.approx(1.0)
    assert batch.record_count == 1


@pytest.mark.anyio
async def test_record_detail_returns_reference_annotations(async_client: AsyncClient, db_session):
    p1, _ = await _get_patients(db_session)
    asr = _make_asr(p1, "hash-a", "肉卵巢大小三九", datetime(2026, 6, 23, 10, 0, 0))
    db_session.add(asr)
    await db_session.flush()
    annotations = [
        {"start": 0, "end": 3, "type": "red", "note": "应为右卵巢"},
        {"start": 6, "end": 8, "type": "orange", "note": "数字格式"},
    ]
    ref = AsrReferenceTranscript(
        patient_id=p1.id,
        record_id=p1.record_id,
        date="20260623",
        base_asr_result_id=asr.id,
        reference_text="右卵巢大小39",
        reference_annotations=annotations,
    )
    db_session.add(ref)
    await db_session.commit()

    record = (
        await async_client.post(f"/conversion-eval/records/from-exam/{p1.id}", json={"asr_result_id": asr.id})
    ).json()

    response = await async_client.get(f"/conversion-eval/records/{record['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["reference_annotations"] == annotations

    judged = await async_client.post(f"/conversion-eval/records/{record['id']}/auto-judge")
    assert judged.status_code == 200
    assert judged.json()["reference_annotations"] == annotations


@pytest.mark.anyio
async def test_record_business_segments_endpoint_returns_locator_rows(async_client: AsyncClient, db_session):
    patient = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A017750"))
    ).scalar_one()
    asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="Test ASR",
        provider="local",
        full_transcript="内膜6.3A型。右卵巢大小39×30，12.1。换边左卵巢大小48×1，29，13.5。无回声。",
        status="success",
    )
    db_session.add(asr)
    await db_session.commit()
    record = (
        await async_client.post(f"/conversion-eval/records/from-exam/{patient.id}", json={"asr_result_id": asr.id})
    ).json()

    response = await async_client.get(f"/conversion-eval/records/{record['id']}/business-segments")

    assert response.status_code == 200
    data = response.json()
    assert data["record_id"] == record["id"]
    assert data["text_source"] == "raw"
    assert any(item["segment_type"] == "medical_term" and item["text"] == "右卵巢大小" for item in data["segments"])
    assert any(item["field_code"] == "left_ovary_size" and item["normalized"] == "48×29" for item in data["segments"])


@pytest.mark.anyio
async def test_get_conversion_record_syncs_reference_created_after_record(async_client: AsyncClient, db_session):
    patient = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A017750"))
    ).scalar_one()
    asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="Test ASR",
        provider="local",
        full_transcript="原始 ASR 文本",
        status="success",
    )
    db_session.add(asr)
    await db_session.commit()

    record = (
        await async_client.post(f"/conversion-eval/records/from-exam/{patient.id}", json={"asr_result_id": asr.id})
    ).json()
    assert record["reference_asr_id"] is None
    assert record["reference_text"] == ""

    reference = AsrReferenceTranscript(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        base_asr_result_id=asr.id,
        reference_text="后补的专家标准 ASR",
        reference_annotations=[{"start": 0, "end": 2, "type": "green", "note": "ok"}],
        is_current=True,
    )
    db_session.add(reference)
    await db_session.commit()

    response = await async_client.get(f"/conversion-eval/records/{record['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["reference_asr_id"] == reference.id
    assert data["reference_text"] == "后补的专家标准 ASR"
    assert data["reference_annotations"] == reference.reference_annotations


@pytest.mark.anyio
async def test_manual_business_segments_are_aggregated_as_rule_candidates(async_client: AsyncClient, db_session):
    patient = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A017750"))
    ).scalar_one()
    asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="Test ASR",
        provider="local",
        full_transcript="面膜十一点一。",
        status="success",
    )
    db_session.add(asr)
    await db_session.commit()
    record = (
        await async_client.post(f"/conversion-eval/records/from-exam/{patient.id}", json={"asr_result_id": asr.id})
    ).json()

    payload = {
        "raw_fragment": "面膜",
        "converted_fragment": "内膜",
        "raw_start": 0,
        "raw_end": 2,
        "category": "endometrium",
        "action_type": "manual_mark",
        "rule_id": "manual_business_segment",
        "rule_version": "manual",
        "risk_type": "medical_term",
        "note": '__manual_business_segment__{"segment_type":"medical_term","field_code":"endometrium","participates":true,"optimize_candidate":true,"reason":"近义词/ASR误识别"}\n面膜应归一为内膜',
    }
    assert (await async_client.post(f"/conversion-eval/records/{record['id']}/details", json=payload)).status_code == 200
    assert (await async_client.post(f"/conversion-eval/records/{record['id']}/details", json=payload)).status_code == 200

    response = await async_client.get("/conversion-eval/rule-candidates")

    assert response.status_code == 200
    candidates = response.json()
    item = next(row for row in candidates if row["raw_fragment"] == "面膜" and row["standard_text"] == "内膜")
    assert item["segment_type"] == "medical_term"
    assert item["field_code"] == "endometrium"
    assert item["occurrence_count"] == 2
    assert item["status"] == "pending"
    assert item["examples"][0]["record_id"] == "A017750"


@pytest.mark.anyio
async def test_mixed_ovary_size_and_remark_candidate_requires_split(async_client: AsyncClient, db_session):
    patient = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A017750"))
    ).scalar_one()
    asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="Test ASR",
        provider="local",
        full_transcript="左卵巢大小五八乘以三八五回声。",
        status="success",
    )
    db_session.add(asr)
    await db_session.commit()
    record = (
        await async_client.post(f"/conversion-eval/records/from-exam/{patient.id}", json={"asr_result_id": asr.id})
    ).json()

    await async_client.post(f"/conversion-eval/records/{record['id']}/details", json={
        "raw_fragment": "五八乘以三八五回声",
        "converted_fragment": "五八乘以三八无回声",
        "raw_start": 5,
        "raw_end": 14,
        "category": "remark",
        "action_type": "manual_mark",
        "rule_id": "manual_business_segment",
        "rule_version": "manual",
        "risk_type": "medical_data",
        "note": '__manual_business_segment__{"segment_type":"medical_data","field_code":"remark","participates":true,"optimize_candidate":true}\n尺寸与备注混合标注',
    })

    response = await async_client.get("/conversion-eval/rule-candidates")

    assert response.status_code == 200
    candidates = response.json()
    item = next(row for row in candidates if row["raw_fragment"] == "五八乘以三八五回声")
    assert item["recommendation"] == "split_required"
    assert "卵巢大小" in item["recommendation_note"]
    assert "备注" in item["recommendation_note"]
    assert item["suggested_splits"] == [
        {
            "raw_fragment": "五八乘以三八",
            "standard_text": "58×38",
            "segment_type": "medical_data",
            "field_code": "ovary_size",
        },
        {
            "raw_fragment": "五回声",
            "standard_text": "无回声",
            "segment_type": "medical_data",
            "field_code": "remark",
        },
    ]


@pytest.mark.anyio
async def test_approve_rule_candidate_creates_disabled_draft_lexicon(async_client: AsyncClient, db_session):
    patient = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A017750"))
    ).scalar_one()
    asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="Test ASR",
        provider="local",
        full_transcript="面膜十一点一。",
        status="success",
    )
    db_session.add(asr)
    await db_session.commit()
    record = (
        await async_client.post(f"/conversion-eval/records/from-exam/{patient.id}", json={"asr_result_id": asr.id})
    ).json()
    await async_client.post(f"/conversion-eval/records/{record['id']}/details", json={
        "raw_fragment": "面膜",
        "converted_fragment": "内膜",
        "raw_start": 0,
        "raw_end": 2,
        "category": "endometrium",
        "action_type": "manual_mark",
        "rule_id": "manual_business_segment",
        "rule_version": "manual",
        "risk_type": "medical_term",
        "note": '__manual_business_segment__{"segment_type":"medical_term","field_code":"endometrium","participates":true,"optimize_candidate":true}\n面膜应归一为内膜',
    })

    response = await async_client.post("/conversion-eval/rule-candidates/approve", json={
        "raw_fragment": "面膜",
        "standard_text": "内膜",
        "segment_type": "medical_term",
        "field_code": "endometrium",
        "note": "从人工候选池审核通过",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["updated_details"] == 1
    assert data["lexicon"]["enabled"] == 0
    lexicon = (
        await db_session.execute(
            select(ConversionLexiconEntry).where(
                ConversionLexiconEntry.error_text == "面膜",
                ConversionLexiconEntry.standard_text == "内膜",
            )
        )
    ).scalar_one()
    assert lexicon.notes and "人工候选池" in lexicon.notes


@pytest.mark.anyio
async def test_run_conversion_preserves_and_applies_manual_business_marks(async_client: AsyncClient, db_session):
    patient = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A017750"))
    ).scalar_one()
    asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="Test ASR",
        provider="local",
        full_transcript="面膜十一点一B型。左卵巢大小五八乘以三八五回声。",
        status="success",
    )
    db_session.add(asr)
    await db_session.commit()
    record = (
        await async_client.post(f"/conversion-eval/records/from-exam/{patient.id}", json={"asr_result_id": asr.id})
    ).json()
    await async_client.post(f"/conversion-eval/records/{record['id']}/details", json={
        "raw_fragment": "五八乘以三八",
        "converted_fragment": "58×38",
        "raw_start": 14,
        "raw_end": 20,
        "category": "left_ovary_size",
        "action_type": "manual_mark",
        "rule_id": "manual_business_segment",
        "rule_version": "manual",
        "risk_type": "medical_data",
        "note": '__manual_business_segment__{"segment_type":"medical_data","field_code":"left_ovary_size","participates":true,"optimize_candidate":true}\n人工修正尺寸',
    })

    response = await async_client.post(f"/conversion-eval/records/{record['id']}/run-conversion")

    assert response.status_code == 200
    data = response.json()
    # 新口径："五回声→无回声"只由医学词规则（C005 REVIEW）决定，业务片段层不硬编码归一
    assert "左卵巢大小58×38五回声" in data["converted_text"]
    manual_details = (
        await db_session.execute(
            select(AsrConversionDetail).where(
                AsrConversionDetail.record_id == record["id"],
                AsrConversionDetail.rule_id == "manual_business_segment",
            )
        )
    ).scalars().all()
    assert len(manual_details) == 1
    assert manual_details[0].raw_fragment == "五八乘以三八"


@pytest.mark.anyio
async def test_business_structure_compare_from_located_segments(async_client: AsyncClient, db_session):
    patient = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A017750"))
    ).scalar_one()
    asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="Test ASR",
        provider="local",
        full_transcript="内膜六点四A型。右卵巢大小三九乘以三零，十六点四。换边左卵巢大小二八乘以二零，十五点二。",
        status="success",
    )
    db_session.add(asr)
    await db_session.commit()
    record = (
        await async_client.post(f"/conversion-eval/records/from-exam/{patient.id}", json={"asr_result_id": asr.id})
    ).json()

    response = await async_client.get(f"/conversion-eval/records/{record['id']}/business-structure-compare")

    assert response.status_code == 200
    data = response.json()
    assert data["extracted"]["endometrium_thickness"] == 6.4
    assert data["extracted"]["endometrium_type"] == "A型"
    assert data["extracted"]["right_follicles"] == [{"size": 16.4, "count": 1}]
    assert data["extracted"]["left_follicles"] == [{"size": 15.2, "count": 1}]
    assert data["ground_truth"]["endometrium_thickness"] == 6.4
    assert data["comparison"]["fields"]["right_follicles"]["match"] is True
    assert data["comparison"]["fields"]["left_follicles"]["match"] is True


# ========== 卵泡明细差异对比 ==========

@pytest.mark.anyio
async def test_business_structure_compare_returns_follicle_diff(async_client: AsyncClient, db_session):
    """单条结构化对比：comparison.fields 保持兼容，顶层新增 follicle_diff（含疑似串边）。"""
    patient = (
        await db_session.execute(select(PatientRecord).where(PatientRecord.record_id == "A017750"))
    ).scalar_one()
    asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="Test ASR",
        provider="local",
        # 右/左卵泡尺寸互换 → 双向疑似串边
        full_transcript="内膜六点四A型。右卵巢大小三九乘以三零，十五点二。换边左卵巢大小二八乘以二零，十六点四。",
        status="success",
    )
    db_session.add(asr)
    await db_session.commit()
    record = (
        await async_client.post(f"/conversion-eval/records/from-exam/{patient.id}", json={"asr_result_id": asr.id})
    ).json()

    response = await async_client.get(f"/conversion-eval/records/{record['id']}/business-structure-compare")

    assert response.status_code == 200
    data = response.json()

    # 兼容：comparison.fields 保持原结构（identified_count/truth_count）
    right_field = data["comparison"]["fields"]["right_follicles"]
    assert right_field["match"] is False
    assert right_field["diff"] == {"identified_count": 1, "truth_count": 1}

    # 新增：顶层 follicle_diff
    fd = data["follicle_diff"]
    assert fd["right_follicles"]["match"] is False
    assert fd["right_follicles"]["missing"] == [{"size": 16.4, "count": 1}]
    assert fd["right_follicles"]["extra"] == [{"size": 15.2, "count": 1}]
    assert fd["right_follicles"]["possible_side_swaps"] == [{"size": 16.4, "count": 1, "opposite_count": 1}]
    assert "疑似串边" in fd["right_follicles"]["summary"]
    assert fd["left_follicles"]["missing"] == [{"size": 15.2, "count": 1}]
    assert fd["left_follicles"]["extra"] == [{"size": 16.4, "count": 1}]
    assert fd["left_follicles"]["possible_side_swaps"] == [{"size": 15.2, "count": 1, "opposite_count": 1}]
    assert fd["summary"] == {
        "missing_total": 2,
        "extra_total": 2,
        "count_mismatch_total": 0,
        "possible_side_swap_total": 2,
    }


@pytest.mark.anyio
async def test_batch_structure_summary_counts_mixed_states(async_client: AsyncClient, db_session):
    """批次汇总：混合 compared / no_ground_truth / failed / no_text 四种状态统计正确。"""
    p1, p2 = await _get_patients(db_session)
    base = datetime(2026, 6, 23, 10, 0, 0)
    db_session.add_all([
        _make_asr(p1, "hash-a", "内膜六点四A型。右卵巢大小三九乘以三零，十六点四。换边左卵巢大小二八乘以二零，十五点二。", base),
        _make_asr(p2, "hash-b", "右卵巢大小三九乘以三零，十六点四。", base),
    ])
    await db_session.commit()

    created = (await async_client.post("/conversion-eval/batches", json={
        "name": "汇总批次",
        "selected_dates": ["20260623"],
        "exam_record_ids": [p1.id, p2.id],
        "asr_source_type": "latest_success",
    })).json()
    batch_id = created["batch"]["id"]
    assert created["created_count"] == 2

    # 手工插入：failed 记录（无 ASR）+ no_text 记录（有 GT 但无文本）+ 差异记录（卵泡互换）
    db_session.add_all([
        AsrConversionRecord(
            batch_id=batch_id, exam_record_id=p2.id, status="failed",
            error_message="无成功ASR", raw_text="", converted_text="",
            conversion_version="manual",
        ),
        AsrConversionRecord(
            batch_id=batch_id, exam_record_id=p1.id, status="ready",
            raw_text="", converted_text="",
            conversion_version="manual",
        ),
        AsrConversionRecord(
            batch_id=batch_id, exam_record_id=p1.id, status="ready",
            raw_text="",
            converted_text="内膜六点四A型。右卵巢大小三九乘以三零，十五点二。换边左卵巢大小二八乘以二零，十六点四。",
            conversion_version="manual",
        ),
    ])
    await db_session.commit()

    response = await async_client.get(f"/conversion-eval/batches/{batch_id}/structure-summary")

    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"] == batch_id
    assert data["record_count"] == 5
    assert data["compared_count"] == 2
    assert data["missing_ground_truth_count"] == 1
    assert data["failed_record_count"] == 1
    assert data["no_text_count"] == 1

    assert data["field_summary"]["right_follicles"] == {"match": 1, "mismatch": 1}
    assert data["field_summary"]["left_follicles"] == {"match": 1, "mismatch": 1}
    assert data["follicle_summary"] == {
        "missing_total": 2,
        "extra_total": 2,
        "count_mismatch_total": 0,
        "possible_side_swap_total": 2,
    }

    compared_match = next(r for r in data["records"] if r["status"] == "compared" and r["right_match"] and r["left_match"])
    assert compared_match["diff_summary"] == ""
    assert compared_match["has_ground_truth"] is True

    compared_diff = next(r for r in data["records"] if r["status"] == "compared" and not r["right_match"])
    assert compared_diff["right_side_swap"] is True
    assert compared_diff["left_side_swap"] is True
    assert "右侧缺失" in compared_diff["diff_summary"]
    assert "疑似串边" in compared_diff["diff_summary"]

    no_gt = next(r for r in data["records"] if r["status"] == "no_ground_truth")
    assert no_gt["has_ground_truth"] is False
    assert no_gt["right_match"] is None

    failed = next(r for r in data["records"] if r["status"] == "failed")
    assert failed["right_match"] is None

    no_text = next(r for r in data["records"] if r["status"] == "no_text")
    assert no_text["has_ground_truth"] is True
