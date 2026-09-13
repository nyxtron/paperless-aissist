"""The queue says which page of a document is being read (issue #54).

Reading a scanned PDF with a vision model takes minutes per document, and the
banner named the step but nothing else, so a slow read looked exactly like a
stuck one. Both vision providers send the pages one by one and now say so.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import scheduler as scheduler_service
from app.services.llm_handler import LLMHandler, _report_page
from app.services.steps.base import StepContext
from app.services.steps.ocr_step import OCRStep


def _idle():
    scheduler_service._clear_processing()
    scheduler_service._save_state(scheduler_service._default_state())


def _active(doc_id: int = 5) -> dict:
    return scheduler_service.get_scheduler_status()["active_documents"][0]


class TestTheStateCarriesThePage:
    def test_a_document_starts_without_one(self):
        _idle()
        scheduler_service.mark_document_started(5, active_step="ocr")

        assert _active()["page"] is None
        assert _active()["pages"] is None

    def test_the_page_lands_on_the_document(self):
        _idle()
        scheduler_service.mark_document_started(5, active_step="ocr")

        scheduler_service.update_active_document(5, page=3, pages=12)

        assert (_active()["page"], _active()["pages"]) == (3, 12)

    def test_the_next_step_is_not_reading_pages(self):
        """Otherwise the banner keeps claiming page 12 of 12 through title and tags."""
        _idle()
        scheduler_service.mark_document_started(5, active_step="ocr")
        scheduler_service.update_active_document(5, page=12, pages=12)

        scheduler_service.update_active_document(5, active_step="title")

        assert _active()["page"] is None
        assert _active()["pages"] is None

    def test_another_document_is_left_alone(self):
        _idle()
        scheduler_service.mark_document_started(5, active_step="ocr")
        scheduler_service.mark_document_started(6, active_step="ocr")

        scheduler_service.update_active_document(5, page=2, pages=4)

        by_id = {
            doc["document_id"]: doc
            for doc in scheduler_service.get_scheduler_status()["active_documents"]
        }
        assert (by_id[5]["page"], by_id[5]["pages"]) == (2, 4)
        assert by_id[6]["page"] is None


class TestReportingNeverBreaksTheRead:
    def test_no_listener_is_fine(self):
        _report_page(None, 1, 3)

    def test_a_listener_that_throws_is_swallowed(self):
        """Progress is a nicety; losing a page of OCR over it would not be."""

        def boom(page, pages):
            raise RuntimeError("state file gone")

        _report_page(boom, 1, 3)

    def test_the_listener_hears_page_and_total(self):
        seen = []
        _report_page(lambda page, pages: seen.append((page, pages)), 2, 7)

        assert seen == [(2, 7)]


class PagesTransport(httpx.AsyncBaseTransport):
    """Answers every vision request with a line of text."""

    def __init__(self):
        self.requests: list[dict] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        if request.url.path.endswith("/api/chat"):
            return httpx.Response(
                200, json={"message": {"content": "page text"}}, request=request
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "page text"}}]},
            request=request,
        )


def _handler(provider: str, api_base: str) -> LLMHandler:
    handler = LLMHandler(provider=provider, model="vision", api_base=api_base)
    handler._client = httpx.AsyncClient(
        base_url=handler.api_base,
        headers={"Content-Type": "application/json"},
        transport=PagesTransport(),
    )
    return handler


class TestBothProvidersReportEveryPage:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider,api_base",
        [("ollama", "http://ollama.test"), ("openai", "http://lmstudio.test/v1")],
    )
    async def test_each_page_is_announced_before_it_is_sent(self, provider, api_base):
        handler = _handler(provider, api_base)
        seen: list[tuple[int, int]] = []

        await handler.vision_complete(
            system_prompt="Read this",
            images=[b"one", b"two", b"three"],
            json_mode=False,
            on_page=lambda page, pages: seen.append((page, pages)),
        )
        await handler.close()

        assert seen == [(1, 3), (2, 3), (3, 3)]

    @pytest.mark.asyncio
    async def test_a_read_without_a_listener_still_works(self):
        handler = _handler("ollama", "http://ollama.test")

        result = await handler.vision_complete(
            system_prompt="Read this", images=[b"one"], json_mode=False
        )
        await handler.close()

        assert "page text" in (result.get("text") or result.get("raw") or "")


class TestTheOcrStepPutsItInTheState:
    @pytest.mark.asyncio
    async def test_the_reporter_writes_the_page_of_the_document_it_belongs_to(
        self, mock_paperless, mock_llm
    ):
        _idle()
        scheduler_service.mark_document_started(1, active_step="ocr")
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"modular_tag_ocr": "ai-ocr", "enable_vision": "true"},
            trigger_tags={"ai-ocr"},
            ocr_text="",
        )
        step = await OCRStep.from_config(ctx.config)

        step._page_reporter(ctx)(4, 9)

        assert (_active()["page"], _active()["pages"]) == (4, 9)

    @pytest.mark.asyncio
    async def test_the_step_hands_the_reporter_to_the_pipeline(
        self, mock_paperless, mock_llm
    ):
        _idle()
        scheduler_service.mark_document_started(1, active_step="ocr")
        pipeline = MagicMock()
        pipeline.llm_handler.provider = "ollama"
        pipeline.llm_handler.model = "vision"

        async def read(pdf_bytes, prompt=None, on_page=None):
            on_page(2, 5)
            return {"text": "Read text"}

        pipeline.extract_text_from_pdf = AsyncMock(side_effect=read)
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"modular_tag_ocr": "ai-ocr", "enable_vision": "true"},
            trigger_tags={"ai-ocr"},
            ocr_text="",
        )
        step = await OCRStep.from_config(ctx.config)
        session = AsyncMock()
        session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=None))
        )

        with (
            patch("app.database.get_async_session") as db,
            patch(
                "app.services.steps.ocr_step.VisionPipeline.create",
                AsyncMock(return_value=pipeline),
            ),
        ):
            db.return_value.__aenter__.return_value = session
            result = await step.execute(ctx)

        assert result.data == {"text": "Read text"}
        assert (_active()["page"], _active()["pages"]) == (2, 5)
