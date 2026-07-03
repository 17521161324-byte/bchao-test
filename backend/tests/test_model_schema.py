from datetime import datetime

from app.schemas import ModelConfigOut


def test_model_output_does_not_expose_credentials():
    model = ModelConfigOut(
        id=1,
        name="Local ASR",
        model_type="asr",
        provider="local",
        endpoint="http://asr.local",
        model_name=None,
        params={},
        is_default=True,
        status="active",
        created_at=datetime(2026, 7, 3),
        updated_at=datetime(2026, 7, 3),
    )
    payload = model.model_dump()
    assert "api_key" not in payload
    assert "api_secret" not in payload
