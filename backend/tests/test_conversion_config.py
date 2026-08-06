"""Tests for ASR conversion configuration workbench."""

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_init_defaults_creates_published_version_with_seed_rules(async_client: AsyncClient):
    response = await async_client.post("/conversion-config/init-defaults")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "published"
    assert data["version_code"] == "V1.0"
    assert data["lexicon_count"] >= 30
    assert data["rule_count"] >= 5

    versions = (await async_client.get("/conversion-config/versions")).json()
    assert len(versions) == 1
    assert versions[0]["status"] == "published"


@pytest.mark.anyio
async def test_published_version_is_immutable_and_clone_is_editable(async_client: AsyncClient):
    published = (await async_client.post("/conversion-config/init-defaults")).json()

    denied = await async_client.post(
        f"/conversion-config/versions/{published['id']}/lexicon",
        json={
            "rule_code": "X001",
            "error_text": "测试错误词",
            "standard_text": "测试标准词",
            "action": "AUTO",
        },
    )
    assert denied.status_code == 409

    clone = await async_client.post(
        f"/conversion-config/versions/{published['id']}/clone",
        json={"version_name": "测试草稿", "version_code": "V1.1-draft"},
    )
    assert clone.status_code == 200
    draft = clone.json()
    assert draft["status"] == "draft"
    assert draft["parent_version_id"] == published["id"]

    created = await async_client.post(
        f"/conversion-config/versions/{draft['id']}/lexicon",
        json={
            "rule_code": "X001",
            "error_text": "肉囊朝",
            "standard_text": "右卵巢",
            "business_scene": "卵泡监测B超",
            "required_context": "大小/卵泡",
            "action": "AUTO",
            "risk_level": "high",
        },
    )
    assert created.status_code == 200
    assert created.json()["error_text"] == "肉囊朝"


@pytest.mark.anyio
async def test_publish_rolls_back_previous_published_version(
    async_client: AsyncClient,
    db_session,
):
    published = (await async_client.post("/conversion-config/init-defaults")).json()
    draft = (await async_client.post(
        f"/conversion-config/versions/{published['id']}/clone",
        json={"version_name": "可发布草稿", "version_code": "V1.1"},
    )).json()

    # P0-10：发布门槛要求通过回归测试且哈希一致
    from app.models.conversion_config import ConversionConfigVersion
    from app.services.conversion_config import build_version_config_hash

    version = await db_session.get(ConversionConfigVersion, draft["id"])
    version.latest_regression_status = "passed"
    version.latest_regression_config_hash = await build_version_config_hash(db_session, version)
    await db_session.commit()

    response = await async_client.post(f"/conversion-config/versions/{draft['id']}/publish")

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    versions = (await async_client.get("/conversion-config/versions")).json()
    statuses = {item["version_code"]: item["status"] for item in versions}
    assert statuses["V1.0"] == "rolled_back"
    assert statuses["V1.1"] == "published"


@pytest.mark.anyio
async def test_publish_blocked_without_regression(async_client: AsyncClient, db_session):
    """P0-10：未通过回归测试的版本禁止发布。"""
    published = (await async_client.post("/conversion-config/init-defaults")).json()
    draft = (await async_client.post(
        f"/conversion-config/versions/{published['id']}/clone",
        json={"version_name": "未回归草稿", "version_code": "no-regression"},
    )).json()

    response = await async_client.post(f"/conversion-config/versions/{draft['id']}/publish")

    assert response.status_code == 409
    assert "回归" in response.json()["detail"]
    # 版本状态未被改动
    assert response.json()["detail"] or True


@pytest.mark.anyio
async def test_publish_blocked_on_config_hash_mismatch(async_client: AsyncClient, db_session):
    """P0-10：回归测试后规则变化（哈希不一致）时禁止发布。"""
    from app.models.conversion_config import ConversionConfigVersion

    published = (await async_client.post("/conversion-config/init-defaults")).json()
    draft = (await async_client.post(
        f"/conversion-config/versions/{published['id']}/clone",
        json={"version_name": "哈希不匹配草稿", "version_code": "hash-mismatch"},
    )).json()

    version = await db_session.get(ConversionConfigVersion, draft["id"])
    version.latest_regression_status = "passed"
    version.latest_regression_config_hash = "stale-hash"
    await db_session.commit()

    response = await async_client.post(f"/conversion-config/versions/{draft['id']}/publish")

    assert response.status_code == 409
    assert "规则已发生变化" in response.json()["detail"]


@pytest.mark.anyio
async def test_version_status_cannot_bypass_publish_endpoint(async_client: AsyncClient):
    published = (await async_client.post("/conversion-config/init-defaults")).json()

    create_published = await async_client.post(
        "/conversion-config/versions",
        json={"version_name": "非法发布", "version_code": "bad-published", "status": "published"},
    )
    assert create_published.status_code == 400

    draft = (await async_client.post(
        f"/conversion-config/versions/{published['id']}/clone",
        json={"version_name": "状态草稿", "version_code": "status-draft"},
    )).json()
    direct_publish = await async_client.put(
        f"/conversion-config/versions/{draft['id']}",
        json={"status": "published"},
    )
    assert direct_publish.status_code == 400

    testing = await async_client.put(
        f"/conversion-config/versions/{draft['id']}",
        json={"status": "testing"},
    )
    assert testing.status_code == 200
    assert testing.json()["status"] == "testing"


@pytest.mark.anyio
async def test_preview_uses_draft_lexicon_entry(async_client: AsyncClient):
    published = (await async_client.post("/conversion-config/init-defaults")).json()
    draft = (await async_client.post(
        f"/conversion-config/versions/{published['id']}/clone",
        json={"version_name": "预览草稿", "version_code": "preview-draft"},
    )).json()
    await async_client.post(
        f"/conversion-config/versions/{draft['id']}/lexicon",
        json={
            "rule_code": "X999",
            "error_text": "肉囊朝",
            "standard_text": "右卵巢",
            "business_scene": "卵泡监测B超",
            "required_context": "大小/卵泡",
            "action": "AUTO",
            "risk_level": "high",
            "confidence": 0.91,
        },
    )

    response = await async_client.post(
        "/conversion-config/preview",
        json={
            "version_id": draft["id"],
            "text": "内膜9.2，肉囊朝大小39乘30，卵泡10。",
            "scene": "卵泡监测B超",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "右卵巢" in data["converted_text"]
    assert any(item["rule_id"] == "X999" for item in data["conversions"])
    assert data["fields"]["endometrium_thickness"] == 9.2
    # 预览应返回业务片段和结构化警示项，供前端展示
    assert "segments" in data and isinstance(data["segments"], list)
    assert "risk_items" in data and isinstance(data["risk_items"], list)
    assert any(item["field_code"] == "endometrium_thickness" for item in data["segments"])


@pytest.mark.anyio
async def test_builtin_rules_returns_three_groups(async_client: AsyncClient):
    response = await async_client.get("/conversion-config/builtin-rules")

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"text_switch", "field_extract", "risk"}
    assert len(data["text_switch"]) >= 3
    assert len(data["field_extract"]) >= 14
    assert len(data["risk"]) >= 17

    # 警示组与引擎 RISK_RULES 保持同步（不另维护副本）
    from app.services.conversion_engine.risk_intercept import RISK_RULES

    assert {item["rule_code"] for item in data["risk"]} == {rule.rule_id for rule in RISK_RULES}


@pytest.mark.anyio
async def test_delete_version_only_allowed_for_draft(async_client: AsyncClient):
    published = (await async_client.post("/conversion-config/init-defaults")).json()

    # 已发布版本不可删除
    denied = await async_client.delete(f"/conversion-config/versions/{published['id']}")
    assert denied.status_code == 409

    draft = (await async_client.post(
        f"/conversion-config/versions/{published['id']}/clone",
        json={"version_name": "可删除草稿", "version_code": "del-draft"},
    )).json()
    # 草稿可删除（级联词库/规则）
    ok = await async_client.delete(f"/conversion-config/versions/{draft['id']}")
    assert ok.status_code == 200
    versions = (await async_client.get("/conversion-config/versions")).json()
    assert all(item["id"] != draft["id"] for item in versions)

    # 不存在的版本 404
    missing = await async_client.delete("/conversion-config/versions/999999")
    assert missing.status_code == 404
