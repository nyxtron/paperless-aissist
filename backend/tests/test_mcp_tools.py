import pytest
from app.mcp.server import is_mcp_enabled

def test_mcp_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MCP_ENABLED", raising=False)
    assert is_mcp_enabled() is False

def test_mcp_enabled_via_env(monkeypatch):
    monkeypatch.setenv("MCP_ENABLED", "true")
    assert is_mcp_enabled() is True


@pytest.mark.asyncio
async def test_list_prompts_returns_names(monkeypatch):
    from app.mcp import server
    stub = {
        "name": "title",
        "prompt_type": "title",
        "is_active": True,
        "document_type_filter": None,
        "system_prompt": "You are a titler.",
        "user_template": "Title this: {content}",
    }
    monkeypatch.setattr(server, "_load_prompts", lambda: [stub])
    out = await server.list_prompts()
    assert out["prompts"][0]["name"] == "title"


from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_get_prompt_happy_path(monkeypatch):
    from app.mcp import server
    stub = {
        "name": "title",
        "prompt_type": "title",
        "is_active": True,
        "document_type_filter": None,
        "system_prompt": "You are a titler.",
        "user_template": "Title this: {content}",
    }
    monkeypatch.setattr(server, "_load_prompts", lambda: [stub])
    out = await server.get_prompt("title")
    assert out["name"] == "title"
    assert out["prompt_type"] == "title"
    assert out["is_active"] is True
    assert out["document_type_filter"] is None
    assert out["system_prompt"] == "You are a titler."
    assert out["user_template"] == "Title this: {content}"


@pytest.mark.asyncio
async def test_get_prompt_not_found(monkeypatch):
    from app.mcp import server
    monkeypatch.setattr(server, "_load_prompts", lambda: [])
    with pytest.raises(ValueError, match="nope"):
        await server.get_prompt("nope")


@pytest.mark.asyncio
async def test_list_pending_maps_trigger_tags(monkeypatch):
    from app.mcp import server
    fake = AsyncMock()
    fake.get_tags = AsyncMock(return_value=[{"id": 5, "name": "ai-process"}])
    fake.list_documents = AsyncMock(return_value=[{"id": 42, "title": "Invoice", "tags": [5]}])
    monkeypatch.setattr(server, "_get_paperless", AsyncMock(return_value=fake))
    monkeypatch.setattr(server, "_trigger_tag_names", lambda: {"ai-process"})
    out = await server.list_pending()
    assert out["documents"] == [{"doc_id": 42, "title": "Invoice", "trigger_tags": ["ai-process"]}]


@pytest.mark.asyncio
async def test_preview_processing_returns_proposed(monkeypatch):
    from app.mcp import server
    monkeypatch.setattr(server, "_get_paperless", AsyncMock(return_value=AsyncMock()))
    class _Proc:
        def __init__(self, p): ...
        async def process_document_preview(self, doc_id):
            return {"document_id": doc_id, "title": "T",
                    "proposed_changes": {"title": "New"},
                    "steps": [{"name": "title", "status": "completed"}]}
    monkeypatch.setattr(server, "DocumentProcessor", _Proc)
    out = await server.preview_processing(42)
    assert out["doc_id"] == 42
    assert out["proposed"]["title"] == "New"


@pytest.mark.asyncio
async def test_process_document_runs_pipeline(monkeypatch):
    from app.mcp import server
    from app.services import scheduler as sched_module
    monkeypatch.setattr(server, "_get_paperless", AsyncMock(return_value=AsyncMock()))
    set_calls = []
    clear_calls = []
    monkeypatch.setattr(sched_module, "_set_processing", lambda *a, **kw: set_calls.append(a))
    monkeypatch.setattr(sched_module, "_clear_processing", lambda: clear_calls.append(1))
    class _Proc:
        def __init__(self, p): ...
        async def process_document(self, doc_id):
            return {"success": True, "steps": [], "document_id": doc_id}
    monkeypatch.setattr(server, "DocumentProcessor", _Proc)
    out = await server.process_document(42)
    assert out["success"] is True
    assert set_calls, "_set_processing was not called"
    assert clear_calls, "_clear_processing was not called"


@pytest.mark.asyncio
async def test_process_all_and_stop(monkeypatch):
    from app.mcp import server
    monkeypatch.setattr(server, "start_automation_processing",
                        AsyncMock(return_value={"status": "started"}))
    monkeypatch.setattr(server, "stop_automation_processing",
                        AsyncMock(return_value={"status": "not_running"}))
    assert (await server.process_all())["status"] == "started"
    assert (await server.stop_processing())["status"] == "not_running"


@pytest.mark.asyncio
async def test_test_prompt_renders_and_runs(monkeypatch):
    from app.mcp import server
    paperless = AsyncMock()
    paperless.get_document = AsyncMock(return_value={"content": "INVOICE 123"})
    monkeypatch.setattr(server, "_get_paperless", AsyncMock(return_value=paperless))
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value={"text": "ok"})
    monkeypatch.setattr(server, "_get_llm", AsyncMock(return_value=llm))
    out = await server.test_prompt(doc_id=42, prompt_text="Find: {content}", system_prompt="sys")
    assert out["model_output"] == "ok"
    assert "INVOICE 123" in out["rendered_prompt"]


@pytest.mark.asyncio
async def test_test_prompt_prompt_name_path(monkeypatch):
    from app.mcp import server

    stub = {
        "name": "title",
        "prompt_type": "title",
        "is_active": True,
        "document_type_filter": None,
        "user_template": "Summarise: {content}",
        "system_prompt": "You are a titler.",
    }

    paperless = AsyncMock()
    paperless.get_document = AsyncMock(return_value={"content": "CONTRACT ABC"})
    monkeypatch.setattr(server, "_get_paperless", AsyncMock(return_value=paperless))
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value={"text": "Generated title"})
    monkeypatch.setattr(server, "_get_llm", AsyncMock(return_value=llm))
    monkeypatch.setattr(server, "_load_prompts", lambda: [stub])

    out = await server.test_prompt(doc_id=42, prompt_name="title")
    assert out["model_output"] == "Generated title"
    assert "CONTRACT ABC" in out["rendered_prompt"]


@pytest.mark.asyncio
async def test_test_prompt_prompt_name_not_found(monkeypatch):
    from app.mcp import server

    stub = {
        "name": "title",
        "prompt_type": "title",
        "is_active": True,
        "document_type_filter": None,
        "user_template": "Summarise: {content}",
        "system_prompt": "You are a titler.",
    }

    paperless = AsyncMock()
    paperless.get_document = AsyncMock(return_value={"content": "WHATEVER"})
    monkeypatch.setattr(server, "_get_paperless", AsyncMock(return_value=paperless))
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value={"text": "x"})
    monkeypatch.setattr(server, "_get_llm", AsyncMock(return_value=llm))
    monkeypatch.setattr(server, "_load_prompts", lambda: [stub])

    with pytest.raises(ValueError, match="nope"):
        await server.test_prompt(doc_id=42, prompt_name="nope")


@pytest.mark.asyncio
async def test_test_prompt_neither_given(monkeypatch):
    from app.mcp import server

    paperless = AsyncMock()
    paperless.get_document = AsyncMock(return_value={"content": "WHATEVER"})
    monkeypatch.setattr(server, "_get_paperless", AsyncMock(return_value=paperless))
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value={"text": "x"})
    monkeypatch.setattr(server, "_get_llm", AsyncMock(return_value=llm))

    with pytest.raises(ValueError, match="Provide"):
        await server.test_prompt(doc_id=42)


@pytest.mark.asyncio
async def test_list_and_get_prompt_against_real_db():
    """Regression: _load_prompts must materialise dicts inside the session.

    Before the fix, reading attributes after session close raised
    DetachedInstanceError.  This test uses the shared test DB (set up by
    conftest.py) to prove the fix holds against a real SQLite engine.
    """
    from app.database import get_session
    from app.models import Prompt
    from app.mcp import server

    unique_name = "test-real-db-prompt-unique-mcp"

    with get_session() as session:
        # Clean up from any prior run, then insert a fresh row.
        existing = session.exec(
            __import__("sqlmodel", fromlist=["select"]).select(Prompt).where(Prompt.name == unique_name)
        ).first()
        if existing:
            session.delete(existing)
            session.commit()

        session.add(
            Prompt(
                name=unique_name,
                prompt_type="title",
                is_active=True,
                document_type_filter=None,
                system_prompt="System: classify this.",
                user_template="User: {content}",
            )
        )
        session.commit()

    # list_prompts must include the new row — attributes read after session closes.
    result = await server.list_prompts()
    names = [p["name"] for p in result["prompts"]]
    assert unique_name in names, f"{unique_name!r} not in {names}"

    # get_prompt must return the row with full fields — no DetachedInstanceError.
    prompt = await server.get_prompt(unique_name)
    assert prompt["system_prompt"] == "System: classify this."
    assert prompt["user_template"] == "User: {content}"
