"""A reply that was cut short is a failure, however much text came with it (#45).

Measured against Ollama and the OpenAI-compatible servers: a page that is simply
blank always ends with "stop", so these checks never fire on the back of a duplex
scan. A page cut off mid-generation, by contrast, hands back partial or invented
text that would otherwise be written to the document as if it had been read.

An absent reason is not a failure — some models leave the field out entirely.
"""

import httpx
import pytest

from app.exceptions import LLMError
from app.services.llm_handler import LLMHandler, _incomplete_reason


class ReplyTransport(httpx.AsyncBaseTransport):
    def __init__(self, body: dict):
        self.body = body

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=self.body, request=request)


def _handler(provider: str, body: dict) -> LLMHandler:
    handler = LLMHandler(provider=provider, model="m", api_base="http://vision.test/v1")
    handler._client = httpx.AsyncClient(
        base_url=handler.api_base,
        headers={"Content-Type": "application/json"},
        transport=ReplyTransport(body),
    )
    return handler


class TestTheReasonIsReadCorrectly:
    def test_a_blank_page_is_not_a_failure(self):
        # Verbatim shape measured from Ollama for a genuinely blank page.
        assert (
            _incomplete_reason(
                {
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 2835,
                    "eval_count": 1,
                }
            )
            is None
        )

    def test_a_cut_off_reply_is_named(self):
        assert _incomplete_reason({"done_reason": "length"}) == "length"

    def test_a_filtered_reply_is_named(self):
        assert (
            _incomplete_reason({"choices": [{"finish_reason": "content_filter"}]})
            == "content_filter"
        )

    def test_a_missing_reason_is_tolerated(self):
        """glm-ocr answers without done_reason at all; that is not a failure."""
        assert _incomplete_reason({"message": {"content": "text"}, "done": False}) is None
        assert _incomplete_reason({}) is None
        assert _incomplete_reason({"choices": []}) is None


@pytest.mark.asyncio
async def test_ollama_refuses_a_page_that_was_cut_off():
    handler = _handler(
        "ollama",
        {"message": {"content": "half a sen"}, "done": True, "done_reason": "length"},
    )

    with pytest.raises(LLMError) as excinfo:
        await handler.vision_complete(
            system_prompt="Read", images=[b"page"], json_mode=False
        )
    await handler.close()

    assert "cut short" in str(excinfo.value)


@pytest.mark.asyncio
async def test_ollama_accepts_a_blank_page():
    handler = _handler(
        "ollama", {"message": {"content": ""}, "done": True, "done_reason": "stop"}
    )

    result = await handler.vision_complete(
        system_prompt="Read", images=[b"page"], json_mode=False
    )
    await handler.close()

    assert result == {"text": ""}


@pytest.mark.asyncio
async def test_openai_refuses_a_page_that_was_cut_off():
    handler = _handler(
        "openai",
        {"choices": [{"message": {"content": "half a sen"}, "finish_reason": "length"}]},
    )

    with pytest.raises(LLMError):
        await handler.vision_complete(
            system_prompt="Read", images=[b"page"], json_mode=False
        )
    await handler.close()


@pytest.mark.asyncio
async def test_openai_accepts_a_blank_page():
    handler = _handler(
        "openai", {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}
    )

    result = await handler.vision_complete(
        system_prompt="Read", images=[b"page"], json_mode=False
    )
    await handler.close()

    assert result == {"text": ""}
