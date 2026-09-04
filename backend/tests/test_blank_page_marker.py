"""A blank page must contribute nothing, not a description of itself (#45).

The OCR prompt asks for raw text and forbids explanations, but says nothing
about a page carrying no text, so the model does the helpful thing and writes
"There is no visible text content in the image." into the document.

Telling it to stay silent does not work — measured against qwen2.5vl, three runs
each: the current prompt, "your entire response must be empty" and "never
describe the image" all still produced a description. A model trained to answer
will answer. Giving it something permitted to say does work, and this is where
that reply is dropped again.
"""

import httpx
import pytest

from app.services.llm_handler import LLMHandler, _drop_no_text_marker


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


class TestTheMarkerIsRecognised:
    @pytest.mark.parametrize("reply", ["NO_TEXT", "no_text", " NO_TEXT ", "NO_TEXT."])
    def test_it_leaves_nothing_behind(self, reply):
        assert _drop_no_text_marker(reply) == ""

    @pytest.mark.parametrize(
        "reply",
        [
            "Rechnungsbetrag EUR 219,40",
            "NO_TEXT was printed on the form",
            "The image contains no text.",
        ],
    )
    def test_real_content_is_untouched(self, reply):
        """Including the description we cannot prevent — that is not ours to eat."""
        assert _drop_no_text_marker(reply) == reply


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "ollama"])
async def test_a_marked_page_reaches_the_document_as_nothing(provider):
    body = (
        {"message": {"content": "NO_TEXT"}, "done": True, "done_reason": "stop"}
        if provider == "ollama"
        else {"choices": [{"message": {"content": "NO_TEXT"}, "finish_reason": "stop"}]}
    )
    handler = _handler(provider, body)

    result = await handler.vision_complete(
        system_prompt="Read", images=[b"page"], json_mode=False
    )
    await handler.close()

    assert result == {"text": ""}
