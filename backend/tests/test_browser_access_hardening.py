"""Other websites cannot read the API, and tokens never travel in the URL."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.main import add_browser_access, parse_cors_origins
from app.origin_guard import OriginGuard


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


FOREIGN = {"Origin": "https://evil.example"}


@pytest.mark.parametrize("path", ["/api/scheduler/stop", "/api/documents/trigger", "/api/config/automation-token"])
def test_another_website_cannot_trigger_a_post_without_body(client, path):
    response = client.post(path, headers={**FOREIGN, "Content-Type": "text/plain"})
    assert response.status_code == 403
    assert "CORS_ALLOW_ORIGINS" in response.json()["detail"]


def test_a_rejected_request_never_reaches_the_route(client):
    with patch("app.routers.scheduler.stop_scheduler") as stop:
        client.post("/api/scheduler/stop", headers=FOREIGN)
    stop.assert_not_called()


def test_the_web_ui_on_the_same_host_passes(client):
    response = client.post("/api/scheduler/stop", headers={"Origin": "http://testserver"})
    assert response.status_code == 200


def test_scripts_without_an_origin_pass(client):
    assert client.post("/api/scheduler/stop").status_code == 200


def _guarded(allowed=()):
    async def route(request):
        return PlainTextResponse("ran")

    return TestClient(Starlette(routes=[Route("/x", route, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])],
                                middleware=[Middleware(OriginGuard, allowed=list(allowed))]))


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        # Plain HTTP on the LAN: browsers send no Sec-Fetch-Site there.
        ({"Host": "192.168.1.5:8000", "Origin": "http://192.168.1.5:8000"}, 200),
        ({"Host": "192.168.1.5:8000", "Origin": "http://192.168.1.5:9000"}, 403),
        ({"Host": "192.168.1.5:8000", "Origin": "http://192.168.1.5"}, 403),
        ({"Host": "SERVER:8000", "Origin": "http://server:8000"}, 200),
        ({"Host": "server:8000", "Origin": "null"}, 403),
        ({"Origin": "null", "Host": ""}, 403),
        # A proxy that rewrites Host but says where the browser went.
        ({"Host": "aissist:8080", "X-Forwarded-Host": "docs.example", "Origin": "http://docs.example"}, 200),
        ({"Host": "aissist:8080", "X-Forwarded-Host": "docs.example, inner", "Origin": "http://docs.example"}, 200),
        ({"Host": "aissist:8080", "X-Forwarded-Host": "docs.example", "Origin": "http://evil.example"}, 403),
        # HTTPS and localhost: the browser says it itself, whatever a proxy did to Host.
        ({"Host": "aissist:8080", "Origin": "https://docs.example", "Sec-Fetch-Site": "same-origin"}, 200),
        ({"Host": "docs.example", "Origin": "https://docs.example", "Sec-Fetch-Site": "cross-site"}, 403),
        ({"Host": "docs.example", "Origin": "https://evil.docs.example", "Sec-Fetch-Site": "same-site"}, 403),
        ({"Host": "docs.example", "Sec-Fetch-Site": "cross-site"}, 403),
        ({"Host": "docs.example", "Sec-Fetch-Site": "none"}, 200),
    ],
)
def test_who_counts_as_the_same_origin(headers, status):
    assert _guarded().post("/x", headers=headers).status_code == status


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_every_changing_method_is_checked(method):
    assert getattr(_guarded(), method)("/x", headers=FOREIGN).status_code == 403


def test_reading_is_left_to_cors():
    assert _guarded().get("/x", headers=FOREIGN).status_code == 200


@pytest.mark.parametrize(
    ("allowed", "headers", "status"),
    [
        (["https://tool.example"], {"Origin": "https://tool.example"}, 200),
        (["https://Tool.example"], {"Origin": "https://tool.example", "Sec-Fetch-Site": "cross-site"}, 200),
        (["https://tool.example"], {"Origin": "https://evil.example"}, 403),
        (["*"], {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}, 200),
    ],
)
def test_listed_origins_pass(allowed, headers, status):
    assert _guarded(allowed).post("/x", headers=headers).status_code == status


def test_a_listed_origin_may_both_read_and_change():
    async def route(request):
        return PlainTextResponse("ran")

    target = FastAPI()
    target.add_route("/x", route, methods=["POST"])
    add_browser_access(target, "https://tool.example")
    browser = TestClient(target)
    listed = browser.post("/x", headers={"Origin": "https://tool.example"})
    assert listed.status_code == 200 and listed.headers["access-control-allow-origin"] == "https://tool.example"
    assert browser.post("/x", headers=FOREIGN).status_code == 403
