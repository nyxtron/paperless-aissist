def test_status_endpoint(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Paperless-AIssist"


def test_auth_disabled_returns_empty(client):
    response = client.get("/api/status")
    assert response.status_code == 200


def test_sensitive_keys_return_404(client):
    """Sensitive config keys should not be accessible via GET /api/config/{key}."""
    response = client.get("/api/config/paperless_token")
    assert response.status_code == 404


def test_nonexistent_key_returns_404(client):
    response = client.get("/api/config/nonexistent_key_xyz")
    assert response.status_code == 404
