"""A reply that was cut short is a failure, however much text came with it (#45).

Measured against Ollama and the OpenAI-compatible servers: a page that is simply
blank always ends with "stop", so these checks never fire on the back of a duplex
scan. A page cut off mid-generation, by contrast, hands back partial or invented
text that would otherwise be written to the document as if it had been read.

An absent reason is not a failure — some models leave the field out entirely.

It is the document that failed, though, not the provider: a run that counted it
as a provider failure stopped after a few dense scans in a row.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import fitz
import httpx
import pytest

from app.exceptions import LLMError, ReplyCutShortError
from app.services import scheduler as scheduler_service
from app.services.llm_handler import LLMHandler, _incomplete_reason
from app.services.steps.base import StepContext
from app.services.steps.ocr_step import OCRStep
from app.services.vision import VisionPipeline


class ReplyTransport(httpx.AsyncBaseTransport):
    def __init__(self, body: dict):
        self.body = body
        self.sent: list[dict] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(json.loads(request.content))
        return httpx.Response(200, json=self.body, request=request)


def _handler(provider: str, body: dict, **settings) -> LLMHandler:
    handler = LLMHandler(provider=provider, model="m", api_base="http://vision.test/v1", **settings)
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

    with pytest.raises(ReplyCutShortError) as excinfo:
        await handler.vision_complete(
            system_prompt="Read", images=[b"page"], json_mode=False
        )
    await handler.close()

    assert "cut short" in str(excinfo.value)
    assert not isinstance(excinfo.value, LLMError)


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

    with pytest.raises(ReplyCutShortError):
        await handler.vision_complete(
            system_prompt="Read", images=[b"page"], json_mode=False
        )
    await handler.close()


@pytest.mark.asyncio
async def test_openai_refuses_a_whole_pdf_that_was_cut_off():
    handler = _handler(
        "openai",
        {"choices": [{"message": {"content": "half a sen"}, "finish_reason": "length"}]},
    )

    with pytest.raises(ReplyCutShortError):
        await handler.vision_complete(
            system_prompt="Read", pdf_bytes=b"%PDF-1.7", json_mode=False
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


# Measured from Ollama 0.40.16 with Nanonets-OCR-s: the page image alone took 2,908
# tokens of the model's own 4,096, and the reply stopped where the window ended.
WINDOW_FULL = {"message": {"content": "Rechnung Nr"}, "done": True, "done_reason": "length",
               "prompt_eval_count": 2908, "eval_count": 1188}


async def _cut_short(body: dict, **settings) -> tuple[str, list[dict]]:
    handler = _handler("ollama", body, **settings)
    with pytest.raises(ReplyCutShortError) as excinfo:
        await handler.vision_complete(system_prompt="Read", images=[b"page"], json_mode=False)
    sent = handler._client._transport.sent
    await handler.close()
    return str(excinfo.value), sent


class TestOllamaPagesHaveAnOutputLimit:
    @pytest.mark.asyncio
    async def test_a_page_writes_4096_tokens_unless_told_otherwise(self):
        handler = _handler("ollama", {"message": {"content": "text"}, "done_reason": "stop"})
        await handler.vision_complete(system_prompt="Read", images=[b"one", b"two"], json_mode=False)
        sent = handler._client._transport.sent
        await handler.close()
        assert [p["options"]["num_predict"] for p in sent] == [4096, 4096]

    @pytest.mark.asyncio
    async def test_the_setting_wins(self):
        handler = _handler("ollama", {"message": {"content": "text"}, "done_reason": "stop"}, max_tokens=6000)
        await handler.vision_complete(system_prompt="Read", images=[b"page"], json_mode=False)
        sent = handler._client._transport.sent
        await handler.close()
        assert sent[0]["options"]["num_predict"] == 6000

    @pytest.mark.asyncio
    async def test_a_page_that_loops_names_the_output_limit(self):
        message, _ = await _cut_short(
            {"message": {"content": "R\nR\nR"}, "done_reason": "length",
             "prompt_eval_count": 2155, "eval_count": 4096}
        )
        assert "output limit of 4096 tokens reached, see Vision Max Output Tokens" in message

    @pytest.mark.asyncio
    async def test_a_raised_limit_is_the_one_named(self):
        message, _ = await _cut_short(
            {"message": {"content": "R"}, "done_reason": "length", "prompt_eval_count": 2155, "eval_count": 6000},
            max_tokens=6000,
        )
        assert "output limit of 6000 tokens reached" in message

    @pytest.mark.asyncio
    async def test_a_full_context_window_names_that_setting(self):
        message, _ = await _cut_short(WINDOW_FULL)
        assert "context window full at 4096 tokens, see Vision Context Window" in message


def test_a_cut_short_page_does_not_count_against_the_provider():
    assert scheduler_service.is_provider_failure(ReplyCutShortError("cut short")) is False


@pytest.mark.asyncio
async def test_the_ocr_step_fails_the_document_and_leaves_the_run_alone(mock_paperless):
    pdf = fitz.open()
    pdf.new_page()
    mock_paperless.get_document_file = AsyncMock(return_value=pdf.tobytes())
    handler = _handler("ollama", WINDOW_FULL)
    config = {"modular_tag_ocr": "ai-ocr", "enable_vision": "true"}
    ctx = StepContext(doc_id=1, paperless=mock_paperless, llm=MagicMock(), config=config,
                      trigger_tags={"ai-ocr"}, ocr_text="")
    step = await OCRStep.from_config(config)
    prompt = MagicMock(system_prompt="Read")
    session = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=prompt)))

    with (
        patch("app.database.get_async_session") as db,
        patch("app.services.steps.ocr_step.VisionPipeline.create",
              AsyncMock(return_value=VisionPipeline(llm_handler=handler))),
    ):
        db.return_value.__aenter__.return_value = session
        result = await step.execute(ctx)
    await handler.close()

    assert "context window full at 4096 tokens" in result.error
    assert ctx.ocr_text == ""
