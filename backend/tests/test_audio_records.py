"""Regression tests for the data-management record list."""
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.models import AudioSeg, PatientAsrResult, PatientLlmResult, PatientRecord


@pytest.mark.anyio
async def test_records_asr_comes_from_latest_llm_execution(
    async_client: AsyncClient,
    db_session,
):
    """The ASR shown for an executed LLM must be the ASR linked by that LLM."""
    patient = (
        await db_session.execute(
            select(PatientRecord).where(PatientRecord.record_id == "A017750")
        )
    ).scalar_one()
    started_at = datetime(2026, 7, 13, 8, 0, 0)

    doubao_asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=5,
        asr_model_name="豆包 ASR",
        provider="volcengine",
        full_transcript="豆包转写结果",
        status="success",
        is_current=False,
        created_at=started_at,
    )
    local_asr = PatientAsrResult(
        patient_id=patient.id,
        record_id=patient.record_id,
        date="20260623",
        asr_model_id=1,
        asr_model_name="本地 FunASR",
        provider="local",
        full_transcript="本地转写结果",
        status="success",
        is_current=True,
        created_at=started_at + timedelta(minutes=1),
    )
    db_session.add_all([doubao_asr, local_asr])
    await db_session.flush()

    previous_current_llm = PatientLlmResult(
        patient_id=patient.id,
        asr_result_id=local_asr.id,
        llm_model_id=4,
        llm_model_name="DeepSeek",
        prompt_content="旧提示词",
        status="success",
        is_current=True,
        created_at=started_at + timedelta(minutes=2),
    )
    latest_llm = PatientLlmResult(
        patient_id=patient.id,
        asr_result_id=doubao_asr.id,
        llm_model_id=4,
        llm_model_name="DeepSeek",
        prompt_content="最新提示词",
        status="failed",
        is_current=False,
        created_at=started_at + timedelta(minutes=3),
    )
    db_session.add_all([previous_current_llm, latest_llm])
    await db_session.commit()

    response = await async_client.get("/audio/records", params={"date": "20260623"})

    assert response.status_code == 200
    record = next(item for item in response.json() if item["id"] == patient.id)
    assert record["latest_asr"]["asr_model_name"] == "本地 FunASR"
    assert record["latest_llm"]["id"] == latest_llm.id
    assert record["latest_llm"]["asr_result_id"] == doubao_asr.id
    assert record["latest_llm"]["asr_model_name"] == "豆包 ASR"
    assert record["latest_llm"]["asr_provider"] == "volcengine"
    assert record["latest_llm"]["asr_status"] == "success"


@pytest.mark.anyio
async def test_audio_file_can_stream_legacy_windows_path_by_seg_id(
    async_client: AsyncClient,
    db_session,
    tmp_path,
    monkeypatch,
):
    """Old E:\\ paths should resolve under the current recordings directory."""
    recordings_dir = tmp_path / "recordings"
    audio_dir = recordings_dir / "20260623" / "A017750" / "1234567890" / "audio"
    audio_dir.mkdir(parents=True)
    wav_path = audio_dir / "seg-0001.wav"
    wav_path.write_bytes(
        b"RIFF"
        + (36).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (16000).to_bytes(4, "little")
        + (32000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + (0).to_bytes(4, "little")
    )
    monkeypatch.setattr(settings, "RECORDINGS_DIR", str(recordings_dir))

    seg = (await db_session.execute(select(AudioSeg))).scalars().first()
    seg.file_path = r"E:\bchao-test\backend\data\recordings\20260623\A017750\1234567890\audio\seg-0001.wav"
    await db_session.commit()

    response = await async_client.get(f"/audio/file/{seg.id}")

    assert response.status_code == 200
    assert response.content.startswith(b"RIFF")
