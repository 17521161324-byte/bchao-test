"""Regression tests for persisted ASR result JSON fields."""

import pytest
from sqlalchemy import select

from app.models import PatientAsrResult, PatientRecord


@pytest.mark.anyio
async def test_patient_asr_segments_track_in_place_append(db_session):
    """Appending ASR segments in place must persist every segment."""
    patient = (
        await db_session.execute(
            select(PatientRecord).where(PatientRecord.record_id == "A017750")
        )
    ).scalar_one()
    result = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="Test ASR",
        provider="local",
        segments=[],
        status="running",
    )
    db_session.add(result)
    await db_session.commit()

    result.segments.append({"seg_index": 1, "text": "第一段"})
    await db_session.commit()
    result.segments.append({"seg_index": 2, "text": "第二段"})
    await db_session.commit()

    db_session.expire_all()
    saved = await db_session.get(PatientAsrResult, result.id)

    assert saved is not None
    assert [item["text"] for item in saved.segments] == ["第一段", "第二段"]
