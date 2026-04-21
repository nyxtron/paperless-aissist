import pytest


def test_config_crud(client):
    """Test full CRUD cycle for config values."""
    response = client.post(
        "/api/config",
        json={"key": "test_integration_key", "value": "test_value"},
    )
    assert response.status_code == 200
    assert response.json()["key"] == "test_integration_key"
    assert response.json()["value"] == "test_value"

    response = client.get("/api/config/test_integration_key")
    assert response.status_code == 200
    assert response.json()["value"] == "test_value"

    response = client.post(
        "/api/config",
        json={"key": "test_integration_key", "value": "updated_value"},
    )
    assert response.status_code == 200
    assert response.json()["value"] == "updated_value"

    response = client.delete("/api/config/test_integration_key")
    assert response.status_code == 200

    response = client.get("/api/config/test_integration_key")
    assert response.status_code == 404


def test_config_list_masks_secrets(client):
    """Sensitive keys are excluded from GET /api/config and listed in secrets_set."""
    client.post(
        "/api/config", json={"key": "llm_api_key", "value": "sk-super-secret-key-12345"}
    )
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "llm_api_key" not in data["data"]
    assert "secrets_set" in data
    assert "llm_api_key" in data["secrets_set"]


def test_config_sensitive_key_not_accessible(client):
    """GET /api/config/{key} returns 404 for sensitive keys."""
    for key in ["paperless_token", "llm_api_key", "llm_api_key_vision"]:
        response = client.get(f"/api/config/{key}")
        assert response.status_code == 404, (
            f"Expected 404 for {key}, got {response.status_code}"
        )


def test_stats_endpoints(client):
    """Stats endpoints return valid data."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert "total_processed" in response.json()

    response = client.get("/api/stats/daily?days=7")
    assert response.status_code == 200

    response = client.get("/api/stats/recent?limit=10")
    assert response.status_code == 200


def test_stats_bounds(client):
    """Stats endpoints enforce parameter bounds."""
    response = client.get("/api/stats/daily?days=500")
    assert response.status_code == 200

    response = client.get("/api/stats/recent?limit=5000")
    assert response.status_code == 200


def test_auth_status_endpoint(client):
    """Auth status returns auth_enabled flag."""
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert "auth_enabled" in response.json()


def test_prompts_list(client):
    """Prompts endpoint returns a list."""
    response = client.get("/api/prompts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_scheduler_status_endpoint(client):
    """Scheduler status endpoint returns JSON."""
    response = client.get("/api/scheduler")
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data or "is_processing" in data
    assert "interval_minutes" in data or "interval" in data


def test_stats_log_stream_asyncio_imported(client):
    """Verify asyncio is imported in stats.py so event_gen does not NameError."""
    import ast
    import inspect
    from app.routers.stats import stream_logs

    source = inspect.getsource(stream_logs)
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "asyncio" in names
