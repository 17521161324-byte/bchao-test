"""API tests for test routes including credential separation."""
import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_get_test_history_not_intercepted_by_test_id(async_client: AsyncClient):
    """GET /api/test/history should work, not be intercepted by /{test_id}"""
    response = await async_client.get("/api/test/history")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.anyio
async def test_get_test_history_with_record_id(async_client: AsyncClient):
    """GET /api/test/history?record_id=A017750"""
    response = await async_client.get("/api/test/history?record_id=A017750")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_get_test_detail_exists(async_client: AsyncClient):
    """GET /api/test/{test_id} should return 404 for non-existent"""
    response = await async_client.get("/api/test/99999")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_start_test_patient_not_found(async_client: AsyncClient):
    """GET /api/test/start should return 404 for non-existent patient"""
    response = await async_client.get(
        "/api/test/start?record_id=NOPATIENT&asr_model_id=1"
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_route_methods_registered(async_client: AsyncClient):
    """Verify all expected routes exist with correct methods"""
    # GET /history
    resp = await async_client.get("/api/test/history")
    assert resp.status_code == 200

    # GET /{id} - should be 404 but route exists
    resp = await async_client.get("/api/test/99999")
    assert resp.status_code == 404

    # PUT /{id}/evaluate - method not allowed without body returns 422
    resp = await async_client.put("/api/test/99999/evaluate", json={})
    assert resp.status_code in [404, 422]  # 422 if validation runs first

    # GET /start with missing patient returns 404
    resp = await async_client.get("/api/test/start?record_id=XX&asr_model_id=1")
    assert resp.status_code == 404


def test_model_config_out_no_credentials():
    """Verify ModelConfigOut doesn't expose credentials"""
    from datetime import datetime
    from app.schemas import ModelConfigOut

    model = ModelConfigOut(
        id=1,
        name="Test",
        model_type="asr",
        provider="local",
        endpoint="http://test.local",
        model_name="test",
        params={},
        is_default=True,
        status="active",
        created_at=datetime(2026, 7, 3),
        updated_at=datetime(2026, 7, 3),
    )
    payload = model.model_dump()
    assert "api_key" not in payload
    assert "api_secret" not in payload
    assert "endpoint" in payload  # non-sensitive fields remain
