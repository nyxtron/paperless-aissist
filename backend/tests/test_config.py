def test_set_and_get_config(client):
    response = client.post(
        "/api/config", json={"key": "test_key", "value": "test_value"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["key"] == "test_key"
    assert data["value"] == "test_value"


def test_get_configs_excludes_secrets(client):
    """Sensitive keys are excluded from GET /api/config and listed in secrets_set."""
    response = client.post(
        "/api/config", json={"key": "llm_api_key", "value": "sk-secret123"}
    )
    assert response.status_code == 200
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "llm_api_key" not in data["data"]
    assert "secrets_set" in data
    assert "llm_api_key" in data["secrets_set"]


def test_sensitive_key_not_in_data(client):
    """paperless_token is never returned in the data field."""
    client.post("/api/config", json={"key": "paperless_token", "value": "tok-123"})
    response = client.get("/api/config")
    data = response.json()
    assert "paperless_token" not in data["data"]
    assert "paperless_token" in data["secrets_set"]


def test_empty_sensitive_key_preserves_existing(client):
    """Saving an empty value for a sensitive key returns existing value."""
    client.post("/api/config", json={"key": "paperless_token", "value": "real-token"})
    response = client.post("/api/config", json={"key": "paperless_token", "value": ""})
    assert response.status_code == 200
    assert response.json()["value"] == "real-token"


def test_config_delete(client):
    client.post("/api/config", json={"key": "test_delete_key", "value": "to_delete"})
    response = client.delete("/api/config/test_delete_key")
    assert response.status_code == 200
    get_response = client.get("/api/config/test_delete_key")
    assert get_response.status_code == 404
