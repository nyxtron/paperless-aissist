"""Unit tests for _MCPEnabledGate — no MCP protocol involved."""

import pytest
from app.mcp.server import _MCPEnabledGate


def _http_scope():
    return {"type": "http"}


def _make_receive():
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


def _make_send():
    messages = []

    async def send(message):
        messages.append(message)

    return send, messages


@pytest.mark.asyncio
async def test_gate_returns_404_when_disabled(monkeypatch):
    """When mcp_enabled is False the gate must respond 404 and not call the inner app."""
    called = []

    async def inner_app(scope, receive, send):
        called.append(True)

    monkeypatch.setattr("app.mcp.server.is_mcp_enabled", lambda: False)

    gate = _MCPEnabledGate(inner_app)
    send, messages = _make_send()
    await gate(_http_scope(), _make_receive(), send)

    assert not called, "inner app should not be called when disabled"
    assert messages[0]["status"] == 404
    assert b"MCP is disabled" in messages[1]["body"]


@pytest.mark.asyncio
async def test_gate_passes_through_when_enabled(monkeypatch):
    """When mcp_enabled is True the gate must delegate to the inner app."""
    called = []

    async def inner_app(scope, receive, send):
        called.append(True)

    monkeypatch.setattr("app.mcp.server.is_mcp_enabled", lambda: True)

    gate = _MCPEnabledGate(inner_app)
    send, messages = _make_send()
    await gate(_http_scope(), _make_receive(), send)

    assert called, "inner app should be called when enabled"
    assert messages == [], "gate should not emit its own response when passing through"
