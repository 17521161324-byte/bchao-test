# -*- coding: utf-8 -*-
"""
单元测试: ExperimentRunner 与 ExperimentWorker

覆盖:
1. ExperimentRunner.run() 成功时 completed_at 写入 datetime (不是 float)
2. 无音频时报错使用 task.patient_id (不是 task.record_id)
3. Worker 执行 runner 时使用新 session (不传已关闭的 session)
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import PatientRecord, AudioSeg, ModelConfig
from app.models.experiment import (
    ExperimentBatch,
    ExperimentCombination,
    ExperimentTask,
    BatchStatus,
    TaskStatus,
    TaskStage,
)
from app.services.experiment_runner import ExperimentRunner


class FakeExecutor:
    async def execute_asr(self, segs, asr_provider, asr_config, hotwords=None, progress_callback=None):
        return {
            "asr_results": [{"seg_index": 1, "text": "测试文本", "duration": 1.0}],
            "full_transcript": "测试文本",
        }

    async def execute_llm(self, transcript, llm_provider, llm_config, prompt_template="", progress_callback=None):
        return {
            "llm_raw_output": "{}",
            "structured_result": {"right_follicle_total": 1},
            "summary_text": "summary",
        }


async def _create_test_data(db, with_seg=True):
    asr_model = ModelConfig(name="Test ASR", model_type="asr", provider="local", endpoint="http://fake")
    db.add(asr_model)
    await db.flush()

    patient = PatientRecord(record_id="A00001", date_folder_id=1, timestamp_folder="1234567890")
    db.add(patient)
    await db.flush()

    if with_seg:
        seg = AudioSeg(patient_id=patient.id, seg_index=1, filename="seg-0001.wav", file_path="/tmp/s.wav", duration=1.0)
        db.add(seg)
        await db.flush()

    batch = ExperimentBatch(name="Test Batch", status=BatchStatus.RUNNING.value)
    db.add(batch)
    await db.flush()

    combo = ExperimentCombination(batch_id=batch.id, asr_model_id=asr_model.id)
    db.add(combo)
    await db.flush()

    task = ExperimentTask(batch_id=batch.id, combination_id=combo.id, patient_id=patient.id, status=TaskStatus.PENDING.value)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task.id, patient.id


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def db_session():
    from app.database import Base, create_async_engine, async_sessionmaker
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    TestSession = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSession() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_runner_writes_datetime_for_completed_at(db_session):
    """成功执行后 completed_at 必须是 datetime, 不能是 float"""
    db = db_session
    task_id, _ = await _create_test_data(db, with_seg=True)

    runner = ExperimentRunner()
    with patch("app.services.experiment_runner.TestExecutor", return_value=FakeExecutor()):
        result = await runner.run(db, task_id)

    assert result["status"] == TaskStatus.SUCCESS.value

    # 重新获取 task
    task = await db.get(ExperimentTask, task_id)
    assert task.completed_at is not None
    assert isinstance(task.completed_at, datetime), (
        f"completed_at 应该是 datetime, 实际为 {type(task.completed_at)}"
    )
    assert isinstance(task.total_duration, float)
    assert task.full_transcript == "测试文本"


@pytest.mark.asyncio
async def test_runner_no_audio_raises_with_patient_id(db_session):
    """无音频时报错使用 task.patient_id, 不访问 task.record_id"""
    db = db_session
    task_id, patient_id = await _create_test_data(db, with_seg=False)

    runner = ExperimentRunner()
    result = await runner.run(db, task_id)

    assert result["status"] == TaskStatus.FAILED.value

    task = await db.get(ExperimentTask, task_id)
    # 错误消息应包含 patient_id
    assert str(patient_id) in (task.error_message or "")
    # 不应出现 "record_id" 属性错误
    assert "record_id" not in (task.error_message or "")


@pytest.mark.asyncio
async def test_worker_creates_new_session_for_runner():
    """Worker 执行 runner 时使用新 session, 不传已关闭的 session"""
    from app.workers.experiment_worker import ExperimentWorker
    import inspect
    source = inspect.getsource(ExperimentWorker.process_one)
    # 验证关键模式
    assert "async with AsyncSessionLocal() as run_db:" in source, "Worker 应在新 session 中执行 runner"
    assert "await runner.run(run_db, task_id)" in source, "runner.run 应使用新 session"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
