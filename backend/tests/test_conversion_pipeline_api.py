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


@pytest.mark.anyio
async def test_fork_from_step_records_lineage_and_commits(async_client: AsyncClient):
    """P0-05：fork（方案 B）新建执行完整重跑，step_code 仅记录为 fork_step_code。"""
    created = (
        await async_client.post(
            "/conversion-pipeline/executions",
            json={
                "source_type": "manual",
                "input_source": "manual",
                "text": "右卵巢大小39×30，16.4",
                "run_mode": "run_all",
            },
        )
    ).json()

    forked = await async_client.post(
        f"/conversion-pipeline/executions/{created['id']}/fork-from-step",
        json={"step_code": "MEDICAL_TERM"},
    )

    assert forked.status_code == 200
    data = forked.json()
    assert data["parent_execution_id"] == created["id"]
    assert data["fork_step_code"] == "MEDICAL_TERM"
    assert data["status"] == "completed"
    assert len(data["steps"]) == 7
    # 方案 B：不改动旧执行
    original = (await async_client.get(f"/conversion-pipeline/executions/{created['id']}")).json()
    assert original["parent_execution_id"] is None
    assert original["fork_step_code"] is None


@pytest.mark.anyio
async def test_run_to_step_stops_after_target_step(async_client: AsyncClient):
    """run-to-step：从最近有效步骤执行到指定步骤后停止。"""
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
    assert created["steps"] == []

    partial = await async_client.post(
        f"/conversion-pipeline/executions/{created['id']}/run-to-step",
        json={"step_code": "MEDICAL_TERM"},
    )
    assert partial.status_code == 200
    data = partial.json()
    assert data["status"] == "running"
    assert [step["step_code"] for step in data["steps"]] == [
        "BASE_CLEANING", "NUMBER_NORMALIZE", "MEDICAL_TERM",
    ]

    full = await async_client.post(
        f"/conversion-pipeline/executions/{created['id']}/run-to-step",
        json={"step_code": "RISK_INTERCEPT"},
    )
    assert full.status_code == 200
    assert full.json()["status"] == "completed"
    assert len(full.json()["steps"]) == 7


@pytest.mark.anyio
async def test_patch_step_output_invalidates_later_steps(async_client: AsyncClient):
    """PATCH 步骤输出：写 manual 输出并返回被失效的后续步骤。"""
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
    await async_client.post(
        f"/conversion-pipeline/executions/{created['id']}/run-to-step",
        json={"step_code": "RISK_INTERCEPT"},
    )

    response = await async_client.patch(
        f"/conversion-pipeline/executions/{created['id']}/steps/BUSINESS_SEGMENT/output",
        json={"manual_output_text": "右卵巢大小39×30，16.4（人工复核）", "edit_note": "补充备注"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["step"]["manual_output_text"] == "右卵巢大小39×30，16.4（人工复核）"
    assert data["step"]["effective_output_text"] == "右卵巢大小39×30，16.4（人工复核）"
    assert data["step"]["edited"] == 1
    assert data["invalidated_step_codes"] == ["FIELD_PARSE", "RUNTIME_RULE", "RISK_INTERCEPT"]


@pytest.mark.anyio
async def test_continue_uses_effective_output(async_client: AsyncClient):
    """continue：用指定步骤的有效输出继续执行后续步骤。"""
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
    await async_client.post(
        f"/conversion-pipeline/executions/{created['id']}/run-to-step",
        json={"step_code": "BUSINESS_SEGMENT"},
    )
    await async_client.patch(
        f"/conversion-pipeline/executions/{created['id']}/steps/BUSINESS_SEGMENT/output",
        json={"manual_output_text": "右卵巢大小39×30，16.4", "edit_note": ""},
    )

    response = await async_client.post(
        f"/conversion-pipeline/executions/{created['id']}/continue",
        json={"from_step_code": "BUSINESS_SEGMENT", "run_mode": "run_all"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert [step["step_code"] for step in data["steps"]] == [
        "BASE_CLEANING", "NUMBER_NORMALIZE", "MEDICAL_TERM",
        "BUSINESS_SEGMENT", "FIELD_PARSE", "RUNTIME_RULE", "RISK_INTERCEPT",
    ]


@pytest.mark.anyio
async def test_list_executions_filters(async_client: AsyncClient):
    await async_client.post(
        "/conversion-pipeline/executions",
        json={"source_type": "manual", "input_source": "manual", "text": "内膜9.2"},
    )
    await async_client.post(
        "/conversion-pipeline/executions",
        json={"source_type": "manual", "input_source": "manual", "text": "右卵巢大小39×30"},
    )

    response = await async_client.get("/conversion-pipeline/executions")
    assert response.status_code == 200
    assert len(response.json()) == 2

    filtered = await async_client.get(
        "/conversion-pipeline/executions",
        params={"source_type": "manual", "limit": 1},
    )
    assert len(filtered.json()) == 1


@pytest.mark.anyio
async def test_create_execution_404_for_missing_rule_version(async_client: AsyncClient):
    """P1-05：不存在的规则版本 ID 返回 404。"""
    response = await async_client.post(
        "/conversion-pipeline/executions",
        json={
            "source_type": "manual",
            "input_source": "manual",
            "text": "右卵巢大小39×30",
            "rule_version_id": 999999,
        },
    )
    assert response.status_code == 404
    assert "规则版本不存在" in response.json()["detail"]
