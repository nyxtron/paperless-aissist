import pytest
from fastmcp import Client
from app.mcp.server import mcp

@pytest.mark.asyncio
async def test_mcp_lists_and_calls_get_status(monkeypatch):
    monkeypatch.setattr(
        "app.mcp.server.get_automation_status",
        lambda: {"success": True, "is_processing": False, "automation_running": False},
    )
    # In-memory client speaks the full MCP protocol (initialize + tools) against the server.
    async with Client(mcp) as client:
        names = [t.name for t in await client.list_tools()]
        assert "get_status" in names
        result = await client.call_tool("get_status", {})
        assert result.data["is_processing"] is False  # confirm accessor (.data) vs fastmcp 2.11
