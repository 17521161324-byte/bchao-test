"""Tests for ASR text validation workflow."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import ModelConfig, PatientAsrResult, PatientRecord, PromptTemplate, TextValidationRun
from app.models.conversion_config import ConversionConfigVersion, ConversionLexiconEntry
from app.routers.text_validation import _normalize_source_spans


def test_normalize_source_spans_repairs_shifted_positions():
    text = "左卵巢大小：40×23，左边18.9。13.3。"
    spans = [
        {"field_code": "left_follicles", "raw_text": "18.9", "start": 17, "end": 21},
        {"field_code": "left_follicles", "raw_text": "13.3", "start": 22, "end": 26},
    ]

    normalized = _normalize_source_spans(spans, text)

    assert text[normalized[0]["start"]:normalized[0]["end"]] == "18.9"
    assert text[normalized[1]["start"]:normalized[1]["end"]] == "13.3"


@pytest.mark.anyio
async def test_create_text_validation_preserves_history_and_evaluates_rule_output(
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
        full_transcript="内膜九点二A型，右卵泡十六点四。",
        status="success",
    )
    llm_model = ModelConfig(
        name="纠错 LLM",
        model_type="llm",
        provider="local",
        endpoint="http://llm.local",
        model_name="local-llm",
        status="active",
    )
    prompt = PromptTemplate(
        name="纠错提示词",
        content="请纠错并输出完整文本：{transcript}",
    )
    db_session.add_all([asr, llm_model, prompt])
    await db_session.commit()

    response = await async_client.post(
        "/text-validation/runs",
        json={
            "exam_record_id": patient.id,
            "asr_result_id": asr.id,
            "llm_model_id": llm_model.id,
            "prompt_template_id": prompt.id,
            "rule_version": "manual",
            "corrected_text_override": "内膜9.2 A型，右卵泡16.4。",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["exam_record_id"] == patient.id
    assert data["asr_result_id"] == asr.id
    assert data["llm_model_name"] == "纠错 LLM"
    assert data["prompt_template_name"] == "纠错提示词"
    assert data["raw_asr_text"] == "内膜九点二A型，右卵泡十六点四。"
    assert data["corrected_text"] == "内膜9.2 A型，右卵泡16.4。"
    assert data["structured_result"]["endometrium_thickness"] == 9.2
    assert data["evaluation"]["total_fields"] == 10
    # 验证运行应持久化命中规则、业务片段和警示项，供前端展示
    assert data["conversions"] == [] or isinstance(data["conversions"], list)
    assert isinstance(data["segments"], list)
    assert isinstance(data["warnings"], list)
    assert isinstance(data["risk_items"], list)

    second = await async_client.post(
        "/text-validation/runs",
        json={
            "exam_record_id": patient.id,
            "asr_result_id": asr.id,
            "llm_model_id": llm_model.id,
            "prompt_template_id": prompt.id,
            "rule_version": "manual",
            "corrected_text_override": "内膜9.2 A型，右卵泡16.4。",
        },
    )
    assert second.status_code == 200

    history = await async_client.get("/text-validation/runs", params={"exam_record_id": patient.id})
    assert history.status_code == 200
    assert len(history.json()) == 2


@pytest.mark.anyio
async def test_text_validation_normalizes_rule_fields_for_comparison(
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
        asr_model_name="Qwen ASR",
        provider="qwen_asr",
        config_hash="hash-qwen",
        full_transcript="内膜9.2 A型，右卵巢大小39×30，16.4。换边，左卵巢大小28×27，15.2。",
        status="success",
    )
    db_session.add(asr)
    await db_session.commit()

    response = await async_client.post(
        "/text-validation/runs",
        json={
            "exam_record_id": patient.id,
            "asr_result_id": asr.id,
            "rule_version": "manual",
            "corrected_text_override": "内膜9.2 A型，右卵巢大小39×30，16.4。换边，左卵巢大小28×27，15.2。",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["structured_result"]["right_follicles"] == [{"size": 16.4, "count": 1}]
    assert data["structured_result"]["right_follicle_total"] == 1
    assert data["structured_result"]["right_ovary_length"] == 39.0
    assert data["structured_result"]["right_ovary_width"] == 30.0
    assert data["evaluation"]["fields"]["right_follicles"]["identified"] == [{"size": 16.4, "count": 1}]
    assert data["source_spans"]
    assert any(item["field_code"] == "endometrium_thickness" for item in data["source_spans"])
    assert any(item["field_code"] == "right_ovary_size" for item in data["source_spans"])


@pytest.mark.anyio
async def test_text_validation_uses_selected_rule_version_lexicon(
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
        asr_model_name="规则 ASR",
        provider="local",
        config_hash="hash-rule",
        full_transcript="内膜9.2，肉囊朝大小39×30，16.4。",
        status="success",
    )
    version = ConversionConfigVersion(
        version_code="validation-draft",
        version_name="验证草稿",
        status="draft",
    )
    db_session.add_all([asr, version])
    await db_session.flush()
    db_session.add(ConversionLexiconEntry(
        version_id=version.id,
        rule_code="X100",
        error_text="肉囊朝",
        standard_text="右卵巢",
        business_scene="卵泡监测B超",
        required_context="大小/卵泡",
        action="AUTO",
        risk_level="high",
        enabled=1,
    ))
    await db_session.commit()

    response = await async_client.post(
        "/text-validation/runs",
        json={
            "exam_record_id": patient.id,
            "asr_result_id": asr.id,
            "rule_version_id": version.id,
            "corrected_text_override": "内膜9.2，肉囊朝大小39×30，16.4。",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["rule_version"] == "validation-draft"
    assert any(item["rule_id"] == "X100" for item in data["conversions"])
    assert data["corrected_text"] == "内膜9.2，肉囊朝大小39×30，16.4。"
    assert data["structured_result"]["right_ovary_length"] == 39.0
    assert any(item["field_code"] == "right_ovary" for item in data["segments"])


@pytest.mark.anyio
async def test_correction_templates_are_independent_from_structured_prompt_templates(
    async_client: AsyncClient,
):
    created = await async_client.post(
        "/text-validation/correction-templates",
        json={
            "name": "完整纠错模板",
            "content": "请输出完整纠错文本：{transcript}",
            "is_default": True,
        },
    )

    assert created.status_code == 200
    assert created.json()["name"] == "完整纠错模板"

    correction_templates = await async_client.get("/text-validation/correction-templates")
    assert correction_templates.status_code == 200
    assert any(item["name"] == "完整纠错模板" for item in correction_templates.json())

    structured_templates = await async_client.get("/prompt-templates")
    assert structured_templates.status_code == 200
    assert not any(item["name"] == "完整纠错模板" for item in structured_templates.json())


@pytest.mark.anyio
async def test_default_correction_template_requires_numeric_blocks(
    async_client: AsyncClient,
):
    response = await async_client.get("/text-validation/correction-templates")

    assert response.status_code == 200
    default = next(item for item in response.json() if item["name"] == "默认完整纠错模板")
    assert "｜" in default["content"]
    assert "右卵巢大小60×35" in default["content"]
    assert "内膜9.5" in default["content"]


@pytest.mark.anyio
async def test_list_validation_runs_tolerates_legacy_null_source_spans(
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
        asr_model_name="旧 ASR",
        provider="legacy",
        config_hash="legacy-hash",
        full_transcript="内膜9.2。",
        status="success",
    )
    db_session.add(asr)
    await db_session.flush()
    db_session.add(TextValidationRun(
        exam_record_id=patient.id,
        asr_result_id=asr.id,
        raw_asr_text=asr.full_transcript,
        corrected_text=asr.full_transcript,
        source_spans=None,
        status="success",
    ))
    await db_session.commit()

    response = await async_client.get("/text-validation/runs", params={"limit": 5})

    assert response.status_code == 200
    assert response.json()[0]["source_spans"] == []
