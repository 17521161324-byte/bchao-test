"""Tests for ASR conversion evaluation P0 workflow."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import AsrReferenceTranscript, PatientAsrResult, PatientRecord


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
