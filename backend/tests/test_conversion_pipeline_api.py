"""流水线调试 API 测试（Task 15）。"""
import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_create_execution_run_all_saves_seven_steps(async_client: AsyncClient):
    response = await async_client.post(
        "/conversion-pipeline/executions",
        json={
            "source_type": "manual",
            "input_source": "manual",
            "text": "右卵巢大小39×30，16.4。换边，左卵巢大小28×27，15.2。",
            "run_mode": "run_all",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert len(data["steps"]) == 7
    codes = [step["step_code"] for step in data["steps"]]
    assert codes == [
        "BASE_CLEANING", "NUMBER_NORMALIZE", "MEDICAL_TERM",
        "BUSINESS_SEGMENT", "FIELD_PARSE", "RUNTIME_RULE", "RISK_INTERCEPT",
    ]
    assert all(step["status"] == "success" for step in data["steps"])
    assert data["config_hash"]
    assert data["result_level"] in ("AUTO_ACCEPT", "REVIEW_REQUIRED", "MANUAL_AUDIO_REVIEW")


@pytest.mark.anyio
async def test_get_execution(async_client: AsyncClient):
    created = (
        await async_client.post(
            "/conversion-pipeline/executions",
            json={
                "source_type": "manual",
                "input_source": "manual",
                "text": "内膜9.2",
                "run_mode": "run_all",
            },
        )
    ).json()

    response = await async_client.get(f"/conversion-pipeline/executions/{created['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert data["input_text"] == "内膜9.2"
    assert len(data["steps"]) == 7


@pytest.mark.anyio
async def test_run_step_progressive(async_client: AsyncClient):
    created = (
        await async_client.post(
            "/conversion-pipeline/executions",
            json={
                "source_type": "manual",
                "input_source": "manual",
                "text": "右卵巢大小39×30，16.4",
                "run_mode": "create_only",
            },
        )
    ).json()
    assert created["status"] == "created"
    assert created["steps"] == []

    step1 = await async_client.post(
        f"/conversion-pipeline/executions/{created['id']}/run-step",
        json={"step_code": "BASE_CLEANING"},
    )
    assert step1.status_code == 200
    assert len(step1.json()["steps"]) == 1
    assert step1.json()["steps"][0]["step_code"] == "BASE_CLEANING"

    # 跳步应被拒绝
    skip = await async_client.post(
        f"/conversion-pipeline/executions/{created['id']}/run-step",
        json={"step_code": "FIELD_PARSE"},
    )
    assert skip.status_code == 400


@pytest.mark.anyio
async def test_compare_executions(async_client: AsyncClient):
    left = (
        await async_client.post(
            "/conversion-pipeline/executions",
            json={"source_type": "manual", "input_source": "manual", "text": "右卵巢大小39×30，16.4"},
        )
    ).json()
    right = (
        await async_client.post(
            "/conversion-pipeline/executions",
            json={"source_type": "manual", "input_source": "manual", "text": "右卵巢大小40×30，16.4"},
        )
    ).json()

    response = await async_client.get(
        "/conversion-pipeline/compare",
        params={"left_execution_id": left["id"], "right_execution_id": right["id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["left_execution_id"] == left["id"]
    assert data["right_execution_id"] == right["id"]
    assert "field_changes" in data
    assert "new_rule_hits" in data
    assert "removed_warnings" in data
