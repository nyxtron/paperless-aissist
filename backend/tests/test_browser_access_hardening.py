"""Other websites cannot read the API, and tokens never travel in the URL."""

from unittest.mock import patch

import pytest

from app.main import parse_cors_origins


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),
        ("", []),
        ("   ", []),
        ("*", ["*"]),
        ("https://a.example, https://b.example,", ["https://a.example", "https://b.example"]),
    ],
)
def test_cors_origins_are_closed_unless_listed(raw, expected):
    assert parse_cors_origins(raw) == expected


def test_a_foreign_origin_gets_no_cors_approval_by_default(client):
    response = client.options(
        "/api/config",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_log_stream_rejects_a_token_in_the_url(client):
    with patch("app.auth._is_auth_enabled", return_value=True):
        response = client.get("/api/stats/logs/stream?token=some-token")
    assert response.status_code == 401
