"""post_json keeps the HTTP status and body so a caller can tell a refused
parameter from a wrong key without parsing the message text."""

import asyncio

import httpx
import pytest

from app.exceptions import LLMError, LLMHttpError, LLMUnavailableError
from app.services.llm_handler import PROMPT_CUTS, LLMHandler


def _handler(respond, provider="ollama"):
    handler = LLMHandler(provider=provider, model="m", api_base="http://llm.test")
    handler._client = httpx.AsyncClient(
        base_url="http://llm.test", transport=httpx.MockTransport(respond)
    )
    return handler


@pytest.mark.asyncio
async def test_a_json_answer_comes_back_as_a_dict():
    handler = _handler(lambda r: httpx.Response(200, json={"ok": 1}))
    assert await handler.post_json("/x", {"a": 1}) == {"ok": 1}
    await handler.close()


@pytest.mark.asyncio
async def test_a_refusal_keeps_status_and_body():
    body = '{"error":{"message":"Unsupported parameter: logprobs","code":"unsupported_parameter"}}'
    handler = _handler(lambda r: httpx.Response(400, text=body))
    with pytest.raises(LLMHttpError) as info:
        await handler.post_json("/x", {})
    assert info.value.status_code == 400
    assert info.value.body == body
    assert isinstance(info.value, LLMError)
    await handler.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [408, 425, 429, 503])
async def test_a_retryable_status_is_still_unavailable(status):
    handler = _handler(lambda r: httpx.Response(status, text="busy"))
    with pytest.raises(LLMUnavailableError):
        await handler.post_json("/x", {})
    await handler.close()


@pytest.mark.asyncio
async def test_a_connection_error_is_unavailable():
    def respond(request):
        raise httpx.ConnectError("gone", request=request)

    handler = _handler(respond)
    with pytest.raises(LLMUnavailableError):
        await handler.post_json("/x", {})
    await handler.close()


@pytest.mark.asyncio
async def test_a_retired_handler_closes_after_the_request():
    started, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        started.set()
        await release.wait()
        return httpx.Response(200, json={})

    handler = _handler(respond)
    running = asyncio.create_task(handler.post_json("/x", {}))
    await started.wait()
    await handler.retire()
    assert not handler._client.is_closed
    release.set()
    await running
    assert handler._client.is_closed


@pytest.mark.asyncio
async def test_a_cut_prompt_is_noted_from_the_count():
    data = {"logprobs": [], "prompt_eval_count": 2050}
    handler = _handler(lambda r: httpx.Response(200, json=data))
    handler.num_ctx = 4096
    token = PROMPT_CUTS.set([])
    try:
        await handler.post_json("/api/chat", {}, prompt_parts=("s", "x" * 20000))
        assert PROMPT_CUTS.get() == [{"evaluated": 2050, "window": 4096}]
    finally:
        PROMPT_CUTS.reset(token)
    await handler.close()


def _ollama(data, context_length):
    """Answers the POST with data and GET /api/ps with the loaded window."""

    def respond(request):
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "m", "context_length": context_length}]})
        return httpx.Response(200, json=data)

    return respond


@pytest.mark.asyncio
async def test_a_cut_prompt_is_noted_from_usage_too():
    data = {"answers": {}, "usage": {"input_tokens": 2050}}
    handler = _handler(_ollama(data, 4096))
    token = PROMPT_CUTS.set([])
    try:
        await handler.post_json("/v1/systemone", {}, prompt_parts=("", "x" * 20000))
        assert PROMPT_CUTS.get() == [{"evaluated": 2050, "window": 4096}]
    finally:
        PROMPT_CUTS.reset(token)
    await handler.close()


@pytest.mark.asyncio
async def test_systemone_is_judged_by_the_server_window_not_num_ctx():
    # /v1/systemone ignores options.num_ctx, so a smaller configured window
    # must not make a prompt that fit the server's look cut.
    data = {"answers": {}, "usage": {"input_tokens": 3000}}
    handler = _handler(_ollama(data, 8192))
    handler.num_ctx = 2048
    token = PROMPT_CUTS.set([])
    try:
        await handler.post_json("/v1/systemone", {}, prompt_parts=("", "x" * 20000))
        assert PROMPT_CUTS.get() == []
    finally:
        PROMPT_CUTS.reset(token)
    await handler.close()


@pytest.mark.asyncio
async def test_chat_is_still_judged_by_num_ctx():
    data = {"logprobs": [], "prompt_eval_count": 2050}
    handler = _handler(_ollama(data, 8192))
    handler.num_ctx = 4096
    token = PROMPT_CUTS.set([])
    try:
        await handler.post_json("/api/chat", {}, prompt_parts=("s", "x" * 20000))
        assert PROMPT_CUTS.get() == [{"evaluated": 2050, "window": 4096}]
    finally:
        PROMPT_CUTS.reset(token)
    await handler.close()


@pytest.mark.asyncio
async def test_a_one_token_answer_is_not_a_cut_off_reply():
    data = {"logprobs": [], "done_reason": "length", "prompt_eval_count": 10}
    handler = _handler(lambda r: httpx.Response(200, json=data))
    assert (await handler.post_json("/api/chat", {}, prompt_parts=("s", "u")))["done_reason"] == "length"
    await handler.close()
