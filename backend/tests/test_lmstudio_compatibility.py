"""LM Studio rejects OpenAI's json_object response format (issue #41).

Its OpenAI-compatible endpoint answers 400 with "'response_format.type' must be
'json_schema' or 'text'". Documents carrying the date tag died on that before
any metadata was written, and custom field extraction swallowed it and reported
success with no fields. Nothing may send response_format any more -- the reply
is parsed leniently instead, which also covers OpenAI rejecting json_object
whenever an edited prompt no longer contains the word "json".
"""

import json

import httpx
import pytest

from app.exceptions import LLMError, LLMUnavailableError
from app.services.llm_handler import LLMHandler

# Verbatim reply from LM Studio 0.4.21 running qwen/qwen2.5-vl-7b once the
# parameter was dropped: valid JSON, wrapped in a markdown fence.
LM_STUDIO_REPLY = (
    "```json\n"
    "{\n"
    '  "created_date": "2026-03-17",\n'
    '  "confidence": "high",\n'
    '  "evidence": "Rechnungsdatum: 17.03.2026."\n'
    "}\n"
    "```"
)

LM_STUDIO_400 = "'response_format.type' must be 'json_schema' or 'text'"


class LMStudioTransport(httpx.AsyncBaseTransport):
    """Answers the way LM Studio does: 400 on response_format, fenced JSON otherwise."""

    def __init__(self, reply: str = LM_STUDIO_REPLY):
        self.requests: list[httpx.Request] = []
        self.reply = reply

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        payload = json.loads(request.content)
        if "response_format" in payload:
            return httpx.Response(400, json={"error": LM_STUDIO_400}, request=request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": self.reply}}]},
            request=request,
        )


def make_handler(transport: httpx.AsyncBaseTransport) -> LLMHandler:
    handler = LLMHandler(
        provider="openai",
        model="qwen/qwen2.5-vl-7b",
        api_base="http://lmstudio.test/v1",
    )
    handler._client = httpx.AsyncClient(
        base_url=handler.api_base,
        headers={"Content-Type": "application/json"},
        transport=transport,
    )
    return handler


@pytest.mark.asyncio
async def test_json_mode_request_succeeds_against_lm_studio():
    transport = LMStudioTransport()
    handler = make_handler(transport)

    result = await handler.complete("system", "user", json_mode=True)
    await handler.close()

    assert result == {
        "created_date": "2026-03-17",
        "confidence": "high",
        "evidence": "Rechnungsdatum: 17.03.2026.",
    }


@pytest.mark.asyncio
async def test_json_mode_never_sends_response_format():
    transport = LMStudioTransport()
    handler = make_handler(transport)

    await handler.complete("system", "user", json_mode=True)
    await handler.close()

    payload = json.loads(transport.requests[0].content)
    assert "response_format" not in payload


@pytest.mark.asyncio
async def test_vision_request_never_sends_response_format():
    transport = LMStudioTransport(reply="page text")
    handler = make_handler(transport)

    await handler.vision_complete(
        system_prompt="Extract text",
        images=[b"page"],
        json_mode=True,
    )
    await handler.close()

    payload = json.loads(transport.requests[0].content)
    assert "response_format" not in payload


class StatusTransport(httpx.AsyncBaseTransport):
    def __init__(self, status: int, body: dict):
        self.status = status
        self.body = body

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self.status, json=self.body, request=request)


@pytest.mark.asyncio
async def test_rejected_request_reports_what_the_server_objected_to():
    """Without the body, #41 could only be diagnosed from LM Studio's own logs."""
    handler = make_handler(StatusTransport(400, {"error": LM_STUDIO_400}))

    with pytest.raises(LLMError) as excinfo:
        await handler.complete("system", "user", json_mode=True)
    await handler.close()

    assert "json_schema" in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 404, 422])
async def test_a_refused_request_is_not_treated_as_a_temporary_outage(status):
    """The processor drops its log entry before retrying, so misfiling these
    would loop the document every scheduler pass without leaving a trace."""
    handler = make_handler(StatusTransport(status, {"error": "nope"}))

    with pytest.raises(LLMError) as excinfo:
        await handler.complete("system", "user", json_mode=True)
    await handler.close()

    assert not isinstance(excinfo.value, LLMUnavailableError)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 500, 503])
async def test_an_overloaded_or_broken_provider_stays_retryable(status):
    handler = make_handler(StatusTransport(status, {"error": "later"}))

    with pytest.raises(LLMUnavailableError):
        await handler.complete("system", "user", json_mode=True)
    await handler.close()


@pytest.mark.asyncio
async def test_an_unreachable_host_stays_retryable():
    class DeadTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host", request=request)

    handler = make_handler(DeadTransport())

    with pytest.raises(LLMUnavailableError):
        await handler.complete("system", "user", json_mode=True)
    await handler.close()
