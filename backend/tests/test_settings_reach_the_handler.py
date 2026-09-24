"""A changed LLM setting reaches the next request without a restart.

The handler is built once and cached. Only provider, model, URL and key used to
drop it, so a new context window, temperature, timeout or output limit saved in
the web UI stayed without effect until the container restarted. Dropping it must
not cut off a request that is still running on it either.
"""

import asyncio
from unittest.mock import patch

import httpx
import pytest

from app.services.config_cache import ConfigCache, get_config_value
from app.services.llm_handler import LLMHandler, LLMHandlerManager


def _ollama_reply(content="ok"):
    return httpx.Response(
        200, json={"message": {"content": content}, "prompt_eval_count": 10}
    )


def _handler_with(respond) -> LLMHandler:
    handler = LLMHandler(provider="ollama", model="m", api_base="http://ollama.test")
    handler._client = httpx.AsyncClient(
        base_url="http://ollama.test", transport=httpx.MockTransport(respond)
    )
    return handler


@pytest.fixture
def cached_handlers():
    text = LLMHandler(provider="ollama", model="m", num_ctx=None)
    vision = LLMHandler(provider="ollama", model="v", num_ctx=None)
    LLMHandlerManager._text_handler = text
    LLMHandlerManager._vision_handler = vision
    yield text, vision
    LLMHandlerManager._text_handler = None
    LLMHandlerManager._vision_handler = None


@pytest.mark.parametrize(
    "key,value",
    [
        ("llm_num_ctx", "16384"),
        ("llm_num_ctx_vision", "8192"),
        ("llm_temperature", "0.3"),
        ("llm_temperature_vision", "0.3"),
        ("llm_timeout", "120"),
        ("llm_timeout_vision", "120"),
        ("llm_max_tokens", "500"),
        ("llm_max_tokens_vision", "500"),
        ("llm_model", "qwen2.5:7b"),
    ],
)
def test_saving_a_setting_drops_the_cached_handler(client, cached_handlers, key, value):
    text, vision = cached_handlers

    response = client.post("/api/config", json={"key": key, "value": value})

    assert response.status_code == 200
    assert LLMHandlerManager._text_handler is None
    assert LLMHandlerManager._vision_handler is None
    assert text.is_closed and vision.is_closed


def test_clearing_a_setting_drops_the_cached_handler(client, cached_handlers):
    client.post("/api/config", json={"key": "llm_num_ctx", "value": "4096"})
    text = LLMHandler(provider="ollama", model="m", num_ctx=4096)
    LLMHandlerManager._text_handler = text

    response = client.delete("/api/config/llm_num_ctx")

    assert response.status_code == 200
    assert LLMHandlerManager._text_handler is None
    assert text.is_closed


def test_other_settings_leave_the_handler_alone(client, cached_handlers):
    text, _ = cached_handlers

    client.post("/api/config", json={"key": "process_tag", "value": "ai-process"})

    assert LLMHandlerManager._text_handler is text
    assert not text.is_closed


async def _cached(key):
    return await (await ConfigCache.get_instance()).get(key)


def test_the_handler_is_dropped_after_the_new_value_is_stored(client, cached_handlers):
    """Dropped earlier, a request in between rebuilds it from the old value."""
    client.post("/api/config", json={"key": "llm_num_ctx", "value": "4096"})
    assert client.portal.call(_cached, "llm_num_ctx") == "4096"
    seen = []

    async def reset():
        seen.append((get_config_value("llm_num_ctx"), await _cached("llm_num_ctx")))

    with patch.object(LLMHandlerManager, "reset", side_effect=reset):
        client.post("/api/config", json={"key": "llm_num_ctx", "value": "16384"})

    assert seen == [("16384", "16384")]


def test_the_handler_is_dropped_after_a_delete_is_stored(client, cached_handlers):
    client.post("/api/config", json={"key": "llm_num_ctx", "value": "4096"})
    seen = []

    async def reset():
        seen.append(get_config_value("llm_num_ctx"))

    with patch.object(LLMHandlerManager, "reset", side_effect=reset):
        client.delete("/api/config/llm_num_ctx")

    assert seen == [None]


def test_the_next_handler_uses_the_saved_window(client, cached_handlers):
    client.post("/api/config", json={"key": "llm_num_ctx", "value": "16384"})
    try:
        handler = client.portal.call(LLMHandlerManager.get_handler)
        assert handler.num_ctx == 16384
    finally:
        client.delete("/api/config/llm_num_ctx")


class TestARunningRequest:
    @pytest.mark.asyncio
    async def test_finishes_when_the_settings_change(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def respond(request):
            started.set()
            await release.wait()
            return _ollama_reply()

        handler = _handler_with(respond)
        LLMHandlerManager._text_handler = handler
        try:
            running = asyncio.create_task(
                handler.complete("s", "u", json_mode=False)
            )
            await started.wait()

            await LLMHandlerManager.reset()

            assert LLMHandlerManager._text_handler is None
            assert not handler._client.is_closed
            release.set()
            assert (await running)["text"] == "ok"
            assert handler.is_closed
            assert handler._client.is_closed
        finally:
            LLMHandlerManager._text_handler = None

    @pytest.mark.asyncio
    async def test_a_vision_request_finishes_too(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def respond(request):
            started.set()
            await release.wait()
            return _ollama_reply("page text")

        handler = _handler_with(respond)
        LLMHandlerManager._vision_handler = handler
        try:
            running = asyncio.create_task(
                handler.vision_complete("s", images=[b"jpeg"], json_mode=False)
            )
            await started.wait()

            await LLMHandlerManager.reset()

            assert not handler._client.is_closed
            release.set()
            await running
            assert handler._client.is_closed
        finally:
            LLMHandlerManager._vision_handler = None

    @pytest.mark.asyncio
    async def test_an_idle_handler_closes_at_once(self):
        handler = _handler_with(lambda request: _ollama_reply())
        LLMHandlerManager._text_handler = handler

        await LLMHandlerManager.reset()

        assert handler.is_closed
        assert handler._client.is_closed

    @pytest.mark.asyncio
    async def test_the_rest_of_a_document_leaves_no_client_open(self):
        """A document keeps its handler for its remaining steps."""
        handler = _handler_with(lambda request: _ollama_reply())
        await handler.retire()
        real_client = httpx.AsyncClient

        def fake_client(**kwargs):
            return real_client(
                transport=httpx.MockTransport(lambda request: _ollama_reply()),
                **kwargs,
            )

        with patch("app.services.llm_handler.httpx.AsyncClient", fake_client):
            result = await handler.complete("s", "u", json_mode=False)

        assert result["text"] == "ok"
        assert handler._client.is_closed

    @pytest.mark.asyncio
    async def test_a_failed_request_still_lets_it_close(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def respond(request):
            started.set()
            await release.wait()
            raise httpx.ConnectError("gone", request=request)

        handler = _handler_with(respond)
        running = asyncio.create_task(handler.complete("s", "u", json_mode=False))
        await started.wait()
        await handler.retire()
        release.set()

        with pytest.raises(Exception):
            await running
        assert handler._client.is_closed

    @pytest.mark.asyncio
    async def test_a_client_that_will_not_close_keeps_the_answer(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def respond(request):
            started.set()
            await release.wait()
            return _ollama_reply()

        handler = _handler_with(respond)
        running = asyncio.create_task(handler.complete("s", "u", json_mode=False))
        await started.wait()
        await handler.retire()

        async def refuse():
            raise RuntimeError("close failed")

        handler.close = refuse
        release.set()

        assert (await running)["text"] == "ok"
