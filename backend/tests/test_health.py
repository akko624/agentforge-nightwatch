from backend.app.core.config import Settings


def test_health_ready_and_openapi(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").status_code == 200
    assert client.get("/api/v1/openapi.json").json()["info"]["title"] == "SQSP API"


def test_unified_error(client):
    response = client.get("/unknown")
    assert response.status_code == 404
    assert response.json()["error"]["request_id"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_config_rejects_unsafe_limits():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(max_entries=0)
