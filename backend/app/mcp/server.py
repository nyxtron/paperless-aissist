"""MCP server for Paperless-AIssist (streamable HTTP, mounted at /mcp)."""

import os

from fastmcp import FastMCP
from sqlmodel import select

from .auth import AissistTokenVerifier
from ..database import get_session
from ..models import Prompt
from ..services.config_cache import get_config_value
from ..services.automation import (
    get_automation_status,
    start_automation_processing,
    stop_automation_processing,
)
from ..services.paperless_manager import PaperlessClientManager
from ..services.processor import DocumentProcessor
from ..services.llm_handler import LLMHandlerManager


def is_mcp_enabled() -> bool:
    """Return True when the MCP surface is turned on (MCP_ENABLED env var).

    Falls back to False (disabled) if the database is not yet initialised (e.g.
    at import time during tests before create_db_and_tables() has run).
    """
    try:
        value = get_config_value("mcp_enabled", "false")
    except Exception:
        value = os.environ.get("MCP_ENABLED", "false")
    return (value or "false").strip().lower() not in ("false", "0", "no", "")


mcp = FastMCP(name="paperless-aissist", auth=AissistTokenVerifier())


@mcp.tool
async def get_status() -> dict:
    """Return the current processing state and the last automation run result."""
    return get_automation_status()


def _load_prompts() -> list[dict]:
    with get_session() as session:
        rows = session.exec(select(Prompt)).all()
        return [
            {
                "name": r.name,
                "prompt_type": r.prompt_type,
                "is_active": r.is_active,
                "document_type_filter": r.document_type_filter,
                "system_prompt": r.system_prompt,
                "user_template": r.user_template,
            }
            for r in rows
        ]


@mcp.tool
async def list_prompts() -> dict:
    """List configured prompts (name, type, active flag, document-type filter)."""
    prompts = _load_prompts()
    return {
        "prompts": [
            {
                "name": p["name"],
                "prompt_type": p["prompt_type"],
                "is_active": p["is_active"],
                "document_type_filter": p["document_type_filter"],
            }
            for p in prompts
        ]
    }


@mcp.tool
async def get_prompt(name: str) -> dict:
    """Return one prompt's full template by name."""
    for p in _load_prompts():
        if p["name"] == name:
            return p
    raise ValueError(f"Prompt not found: {name}")


MODULAR_TAG_KEYS = (
    "process_tag", "modular_tag_process", "modular_tag_ocr", "modular_tag_ocr_fix",
    "modular_tag_date", "modular_tag_title", "modular_tag_correspondent",
    "modular_tag_document_type", "modular_tag_tags", "modular_tag_fields",
)


async def _get_paperless():
    return await PaperlessClientManager.get_client()


def _trigger_tag_names() -> set[str]:
    names = set()
    defaults = {"process_tag": "ai-process", "modular_tag_process": "ai-process"}
    for key in MODULAR_TAG_KEYS:
        names.add(get_config_value(key, defaults.get(key, key.replace("modular_tag_", "ai-"))))
    return {n for n in names if n}


@mcp.tool
async def list_pending() -> dict:
    """List documents that currently carry a processing trigger tag."""
    paperless = await _get_paperless()
    all_tags = await paperless.get_tags()
    wanted = _trigger_tag_names()
    name_by_id = {t["id"]: t["name"] for t in all_tags}
    trigger_ids = [t["id"] for t in all_tags if t["name"] in wanted]
    docs = await paperless.list_documents(tags_any=trigger_ids) if trigger_ids else []
    return {
        "documents": [
            {
                "doc_id": d["id"],
                "title": d.get("title"),
                "trigger_tags": sorted(
                    tag_name
                    for tid in d.get("tags", [])
                    if (tag_name := name_by_id.get(tid)) is not None and tag_name in wanted
                ),
            }
            for d in docs
        ]
    }


@mcp.tool
async def preview_processing(doc_id: int) -> dict:
    """Dry-run: show what processing would change for a document, writing nothing."""
    paperless = await _get_paperless()
    result = await DocumentProcessor(paperless).process_document_preview(doc_id)
    return {
        "doc_id": result.get("document_id", doc_id),
        "title": result.get("title"),
        "proposed": result.get("proposed_changes", {}),
        "steps": result.get("steps", []),
    }


@mcp.tool
async def process_document(doc_id: int) -> dict:
    """Run the full ai-process pipeline on one document and write results to Paperless."""
    from ..services.scheduler import _set_processing, _clear_processing
    paperless = await _get_paperless()
    _set_processing(doc_id)
    try:
        return await DocumentProcessor(paperless).process_document(doc_id)
    finally:
        _clear_processing()


@mcp.tool
async def process_all() -> dict:
    """Start processing all tagged documents in the background (idempotent)."""
    return await start_automation_processing()


@mcp.tool
async def stop_processing() -> dict:
    """Request cancellation of the current background processing run."""
    return await stop_automation_processing()


async def _get_llm():
    return await LLMHandlerManager.get_handler(for_vision=False)


@mcp.tool
async def test_prompt(
    doc_id: int,
    prompt_name: str | None = None,
    prompt_text: str | None = None,
    system_prompt: str | None = None,
) -> dict:
    """Render a prompt against a document's text and return the raw model output (no writes)."""
    system = system_prompt or ""
    template = prompt_text
    if prompt_name:
        for p in _load_prompts():
            if p["name"] == prompt_name:
                template = p["user_template"]
                system = system_prompt or p["system_prompt"]
                break
        else:
            raise ValueError(f"Prompt not found: {prompt_name}")
    if not template:
        raise ValueError("Provide prompt_name or prompt_text")

    paperless = await _get_paperless()
    doc = await paperless.get_document(doc_id)
    rendered = template.replace("{content}", doc.get("content", "") or "")

    llm = await _get_llm()
    result = await llm.complete(system, rendered, json_mode=False)
    return {"rendered_prompt": rendered, "model_output": result.get("text", "")}


class _MCPEnabledGate:
    """Pure-ASGI middleware that returns 404 when MCP is disabled.

    Must be raw ASGI (not BaseHTTPMiddleware) so it does not buffer the
    request/response body — buffering breaks streamable HTTP sessions.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not is_mcp_enabled():
            await send(
                {
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"detail":"MCP is disabled"}',
                }
            )
            return
        await self.app(scope, receive, send)


def build_mcp_app():
    """Return the stateless streamable-HTTP ASGI app served at /mcp/ when mounted at /mcp.

    The gate middleware checks the live mcp_enabled config on every request so
    the MCP surface can be toggled via the web UI without a server restart.
    """
    from starlette.middleware import Middleware

    return mcp.http_app(
        path="/",
        stateless_http=True,
        json_response=True,
        middleware=[Middleware(_MCPEnabledGate)],
    )
