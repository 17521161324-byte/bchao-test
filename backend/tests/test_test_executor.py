import pytest

from app.services.test_executor import TestExecutor
from app.services.llm import LLMResponse


class FakeASR:
    async def transcribe(self, audio_path, hotwords=None):
        suffix = ",".join(hotwords or [])
        return f"{audio_path}:{suffix}"


class FakeLLM:
    async def extract(self, transcript, prompt_template):
        return LLMResponse(
            raw_text="raw",
            structured={"right_follicle_total": 2},
            summary="summary",
        )


@pytest.mark.asyncio
async def test_asr_and_llm_stages_run_independently(monkeypatch):
    monkeypatch.setattr("app.services.test_executor.create_asr", lambda provider, **config: FakeASR())
    monkeypatch.setattr("app.services.test_executor.create_llm", lambda provider, **config: FakeLLM())
    executor = TestExecutor()

    asr = await executor.execute_asr(
        segs=[{"seg_index": 1, "file_path": "one.wav", "duration": 1.0}],
        asr_provider="fake",
        asr_config={},
        hotwords=["卵泡"],
    )
    llm = await executor.execute_llm(
        transcript=asr["full_transcript"],
        llm_provider="fake",
        llm_config={},
        prompt_template="{transcript}",
    )

    assert asr["asr_results"][0]["text"] == "one.wav:卵泡"
    assert llm["structured_result"] == {"right_follicle_total": 2}


@pytest.mark.asyncio
async def test_execute_combines_stages(monkeypatch):
    """Test that execute() correctly combines ASR + LLM + timing"""
    monkeypatch.setattr("app.services.test_executor.create_asr", lambda provider, **config: FakeASR())
    monkeypatch.setattr("app.services.test_executor.create_llm", lambda provider, **config: FakeLLM())
    executor = TestExecutor()

    result = await executor.execute(
        segs=[{"seg_index": 1, "file_path": "a.wav", "duration": 1.0}],
        asr_provider="fake",
        asr_config={"hotwords": ["热词"]},
        llm_provider="fake",
        llm_config={"model_name": "test"},
    )

    assert result is not None
    assert len(result["asr_results"]) == 1
    assert result["asr_results"][0]["text"] == "a.wav:热词"
    assert result["full_transcript"] == "a.wav:热词"
    assert result["structured_result"] == {"right_follicle_total": 2}
    assert result["summary_text"] == "summary"
    assert result["duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_execute_asr_only_no_llm(monkeypatch):
    """Test execute() with ASR only (no LLM)"""
    monkeypatch.setattr("app.services.test_executor.create_asr", lambda provider, **config: FakeASR())
    executor = TestExecutor()

    result = await executor.execute(
        segs=[{"seg_index": 1, "file_path": "a.wav", "duration": 1.0}],
        asr_provider="fake",
        asr_config={},
    )

    assert result is not None
    assert len(result["asr_results"]) == 1
    assert result["llm_raw_output"] is None
    assert result["structured_result"] is None


@pytest.mark.asyncio
async def test_execute_empty_segs(monkeypatch):
    """Test execute() with empty segments"""
    monkeypatch.setattr("app.services.test_executor.create_asr", lambda provider, **config: FakeASR())
    executor = TestExecutor()

    result = await executor.execute(
        segs=[],
        asr_provider="fake",
        asr_config={},
    )

    assert result is not None
    assert result["asr_results"] == []
    assert result["full_transcript"] == ""
