"""A prompt Ollama had to cut is reported, not silently used.

With no context window configured, Ollama runs a model with its own default,
4,096 tokens on most machines. A longer prompt is cut to about half the window
keeping only the first four tokens and the tail: the system prompt shrinks to a
word and the option lists disappear. Ollama logs it on its own side only. On a
real archive this wrote model chatter as a document title.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.llm_handler import (
    PROMPT_CUTS,
    LLMHandler,
    _prompt_chars,
    _prompt_was_cut,
)
from app.services.processor import DocumentProcessor
from app.services.steps.base import StepResult


class TestTellingACutPrompt:
    def test_the_measured_case(self):
        """Document 89: 8,558 prompt tokens, a 4,096 window, 2,050 evaluated."""
        assert _prompt_was_cut(10_260, 2_050, 4_096) is True

    def test_the_same_case_without_knowing_the_window(self):
        assert _prompt_was_cut(12_400, 2_050, None) is True

    def test_a_prompt_that_fits(self):
        assert _prompt_was_cut(3_825, 1_478, 4_096) is False
        assert _prompt_was_cut(12_000, 3_614, 4_096) is False

    def test_an_older_ollama_that_fills_the_window_with_the_tail(self):
        assert _prompt_was_cut(6_000, 4_095, 4_096) is True

    def test_other_window_sizes(self):
        assert _prompt_was_cut(20_000, 8_194, 16_384) is True
        assert _prompt_was_cut(20_000, 8_193, 16_384) is False

    def test_no_count_no_verdict(self):
        assert _prompt_was_cut(50_000, None, 4_096) is False
        assert _prompt_was_cut(50_000, 0, None) is False

    def test_a_known_window_outweighs_the_text_length(self):
        """Ollama only ever cuts to one of two sizes; any other count fit."""
        assert _prompt_was_cut(6_000, 1_000, 4_096) is False
        assert _prompt_was_cut(60_000, 2_049, 4_096) is False


class TestCountingCharacters:
    def test_whitespace_counts_once(self):
        assert _prompt_chars("a  \n\n  b") == 3

    def test_runs_of_one_mark_count_once(self):
        """Measured on qwen2.5: a separator line takes one token per 40 characters."""
        assert _prompt_chars("-" * 80) == 1
        assert _prompt_chars("Name: " + "_" * 60) == len("Name: _")
        assert _prompt_chars("Betrag " + "." * 60 + " 12,00") == len("Betrag . 12,00")

    def test_letters_are_left_alone(self):
        assert _prompt_chars("R e c h n u n g") == 15
        assert _prompt_chars("Aachen") == 6

    def test_system_and_user_prompt_both_count(self):
        assert _prompt_chars("abc", "de") == 5


class OllamaTransport(httpx.AsyncBaseTransport):
    def __init__(self, evaluated: int, loaded_window=None, loaded_name="qwen2.5:7b"):
        self.evaluated = evaluated
        self.loaded_window = loaded_window
        self.loaded_name = loaded_name
        self.paths: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path == "/api/ps":
            models = []
            if self.loaded_window:
                models.append({"name": self.loaded_name, "model": self.loaded_name,
                               "context_length": self.loaded_window})
            return httpx.Response(200, json={"models": models}, request=request)
        return httpx.Response(
            200,
            json={"message": {"content": "Title"}, "prompt_eval_count": self.evaluated, "eval_count": 3},
            request=request,
        )


def _handler(transport, num_ctx=None, model="qwen2.5:7b"):
    handler = LLMHandler(provider="ollama", model=model, api_base="http://ollama.test", num_ctx=num_ctx)
    handler._client = httpx.AsyncClient(base_url="http://ollama.test", transport=transport)
    return handler


LONG_PROMPT = "e n M i t g l i e d " * 1_200  # spaced-out OCR text like document 89


class TestTheHandlerReportsIt:
    @pytest.mark.asyncio
    async def test_a_cut_is_recorded_for_the_running_step(self):
        handler = _handler(OllamaTransport(evaluated=2_050, loaded_window=4_096))
        token = PROMPT_CUTS.set([])
        try:
            with patch("app.services.llm_handler.logger") as log:
                await handler.complete("System.", LONG_PROMPT, json_mode=False)
            cuts = PROMPT_CUTS.get()
        finally:
            PROMPT_CUTS.reset(token)
        await handler.close()

        assert cuts == [{"evaluated": 2_050, "window": 4_096}]
        assert "cut the prompt" in log.warning.call_args.args[0]

    @pytest.mark.asyncio
    async def test_a_configured_window_needs_no_lookup(self):
        transport = OllamaTransport(evaluated=8_194)
        handler = _handler(transport, num_ctx=16_384)
        token = PROMPT_CUTS.set([])
        try:
            await handler.complete("System.", LONG_PROMPT * 4, json_mode=False)
            cuts = PROMPT_CUTS.get()
        finally:
            PROMPT_CUTS.reset(token)
        await handler.close()

        assert cuts == [{"evaluated": 8_194, "window": 16_384}]
        assert "/api/ps" not in transport.paths

    @pytest.mark.asyncio
    async def test_a_prompt_that_fits_records_nothing(self):
        handler = _handler(OllamaTransport(evaluated=1_478, loaded_window=4_096))
        token = PROMPT_CUTS.set([])
        try:
            await handler.complete("System.", "kurzer Brief " * 200, json_mode=False)
            cuts = PROMPT_CUTS.get()
        finally:
            PROMPT_CUTS.reset(token)
        await handler.close()

        assert cuts == []

    @pytest.mark.asyncio
    async def test_ollamas_window_is_read_once_and_reused(self):
        transport = OllamaTransport(evaluated=2_050, loaded_window=4_096)
        handler = _handler(transport)

        for _ in range(3):
            await handler.complete("System.", LONG_PROMPT, json_mode=False)
        await handler.close()

        assert transport.paths.count("/api/ps") == 1

    @pytest.mark.asyncio
    async def test_the_implicit_latest_tag_matches(self):
        transport = OllamaTransport(evaluated=2_050, loaded_window=4_096, loaded_name="qwen2.5:latest")
        handler = _handler(transport, model="qwen2.5")
        token = PROMPT_CUTS.set([])
        try:
            await handler.complete("System.", "kurz " * 300, json_mode=False)
            cuts = PROMPT_CUTS.get()
        finally:
            PROMPT_CUTS.reset(token)
        await handler.close()

        # 1,500 short characters in 2,050 tokens could be a natural prompt; only
        # the window read from Ollama shows it is the cut size.
        assert cuts == [{"evaluated": 2_050, "window": 4_096}]

    @pytest.mark.asyncio
    async def test_outside_a_step_nothing_breaks(self):
        handler = _handler(OllamaTransport(evaluated=2_050, loaded_window=4_096))

        result = await handler.complete("System.", LONG_PROMPT, json_mode=False)
        await handler.close()

        assert result == {"text": "Title"}

    @pytest.mark.asyncio
    async def test_a_failing_lookup_falls_back_to_the_text_length(self):
        class NoPs(OllamaTransport):
            async def handle_async_request(self, request):
                if request.url.path == "/api/ps":
                    raise httpx.ConnectError("gone", request=request)
                return await super().handle_async_request(request)

        handler = _handler(NoPs(evaluated=2_050))
        token = PROMPT_CUTS.set([])
        try:
            await handler.complete("System.", LONG_PROMPT, json_mode=False)
            cuts = PROMPT_CUTS.get()
        finally:
            PROMPT_CUTS.reset(token)
        await handler.close()

        assert cuts == [{"evaluated": 2_050, "window": None}]

    @pytest.mark.asyncio
    async def test_the_system_prompt_counts_as_well(self):
        class NoPs(OllamaTransport):
            async def handle_async_request(self, request):
                if request.url.path == "/api/ps":
                    raise httpx.ConnectError("gone", request=request)
                return await super().handle_async_request(request)

        handler = _handler(NoPs(evaluated=2_050))
        token = PROMPT_CUTS.set([])
        try:
            await handler.complete("Nimm nur Namen aus der Liste. " * 400, "kurz", json_mode=False)
            cuts = PROMPT_CUTS.get()
        finally:
            PROMPT_CUTS.reset(token)
        await handler.close()

        assert cuts == [{"evaluated": 2_050, "window": None}]

    @pytest.mark.asyncio
    async def test_a_form_full_of_lines_is_not_taken_for_a_cut(self):
        """Without a window only the text length is left; long lines must not fool it."""

        class NoPs(OllamaTransport):
            async def handle_async_request(self, request):
                if request.url.path == "/api/ps":
                    raise httpx.ConnectError("gone", request=request)
                return await super().handle_async_request(request)

        form = ("Name: " + "_" * 60 + "\n" + "-" * 80 + "\n") * 60
        handler = _handler(NoPs(evaluated=1_200))
        token = PROMPT_CUTS.set([])
        try:
            await handler.complete("System.", form, json_mode=False)
            cuts = PROMPT_CUTS.get()
        finally:
            PROMPT_CUTS.reset(token)
        await handler.close()

        assert cuts == []

    @pytest.mark.asyncio
    async def test_a_lookup_that_found_nothing_is_tried_again_soon(self):
        transport = OllamaTransport(evaluated=2_050, loaded_window=None)
        handler = _handler(transport)
        clock = [1_000.0]

        with patch("app.services.llm_handler.time.monotonic", lambda: clock[0]):
            await handler.complete("System.", LONG_PROMPT, json_mode=False)
            clock[0] += 30
            await handler.complete("System.", LONG_PROMPT, json_mode=False)
            assert transport.paths.count("/api/ps") == 1

            transport.loaded_window = 4_096
            clock[0] += 31
            token = PROMPT_CUTS.set([])
            try:
                await handler.complete("System.", "kurz " * 300, json_mode=False)
                cuts = PROMPT_CUTS.get()
            finally:
                PROMPT_CUTS.reset(token)
            assert transport.paths.count("/api/ps") == 2
            assert cuts == [{"evaluated": 2_050, "window": 4_096}]

            clock[0] += 300
            await handler.complete("System.", LONG_PROMPT, json_mode=False)
            assert transport.paths.count("/api/ps") == 2
        await handler.close()

    @pytest.mark.asyncio
    async def test_the_lookup_does_not_wait_as_long_as_a_completion(self):
        timeouts = []

        class Recording(OllamaTransport):
            async def handle_async_request(self, request):
                if request.url.path == "/api/ps":
                    timeouts.append(request.extensions["timeout"]["read"])
                return await super().handle_async_request(request)

        handler = _handler(Recording(evaluated=2_050, loaded_window=4_096))
        handler._client = httpx.AsyncClient(
            base_url="http://ollama.test", transport=handler._client._transport, timeout=600
        )
        await handler.complete("System.", LONG_PROMPT, json_mode=False)
        await handler.close()

        assert timeouts and timeouts[0] <= 10


def _processor(mock_paperless, step):
    mock_paperless.get_document = AsyncMock(
        return_value={"id": 89, "title": "Scan", "content": "x", "tags": [1]}
    )
    processor = DocumentProcessor(paperless=mock_paperless)
    processor._build_steps = AsyncMock(return_value=[step])
    processor._get_config_dict = AsyncMock(return_value={"modular_tag_title": "ai-title"})
    processor._get_config = AsyncMock(side_effect=lambda k, d=None: d)
    processor._fetch_metadata = AsyncMock(
        return_value={
            "tags": [{"id": 1, "name": "ai-title"}],
            "correspondents": [],
            "document_types": [],
            "custom_fields": [],
        }
    )
    processor._apply_metadata_update = AsyncMock()
    processor._apply_tag_updates = AsyncMock()
    processor._log_processing = AsyncMock(return_value=7)
    return processor


def _title_step(cut: bool, second_step_calls_llm=False):
    async def execute(ctx):
        if cut:
            PROMPT_CUTS.get().append({"evaluated": 2_050, "window": 4_096})
        return StepResult(data={"title": "Beitragsbescheid"})

    step = MagicMock()
    step.name = "title"
    step.can_handle.return_value = True
    step.execute = AsyncMock(side_effect=execute)
    step.update_metadata = AsyncMock()
    return step


class TestTheRunShowsIt:
    @pytest.mark.asyncio
    async def test_the_step_that_saw_half_a_prompt_says_so(self, mock_paperless, mock_llm):
        processor = _processor(mock_paperless, _title_step(cut=True))

        with patch("app.services.processor.LLMHandlerManager.get_handler", AsyncMock(return_value=mock_llm)):
            result = await processor.process_document(89)

        title = next(s for s in result["steps"] if s["name"] == "title")
        assert title["details"]["prompt_cut"] == {"evaluated": 2_050, "window": 4_096}
        stored = json.loads(processor._log_processing.await_args.kwargs["llm_response"])
        assert stored["steps"][0]["details"]["prompt_cut"]["evaluated"] == 2_050

    @pytest.mark.asyncio
    async def test_a_step_that_fit_carries_no_warning(self, mock_paperless, mock_llm):
        processor = _processor(mock_paperless, _title_step(cut=False))

        with patch("app.services.processor.LLMHandlerManager.get_handler", AsyncMock(return_value=mock_llm)):
            result = await processor.process_document(89)

        title = next(s for s in result["steps"] if s["name"] == "title")
        assert "prompt_cut" not in (title.get("details") or {})

    @pytest.mark.asyncio
    async def test_a_cut_does_not_leak_into_the_next_step(self, mock_paperless, mock_llm):
        second = _title_step(cut=False)
        second.name = "tags"
        processor = _processor(mock_paperless, _title_step(cut=True))
        processor._build_steps = AsyncMock(return_value=[_title_step(cut=True), second])

        with patch("app.services.processor.LLMHandlerManager.get_handler", AsyncMock(return_value=mock_llm)):
            result = await processor.process_document(89)

        by_name = {s["name"]: s for s in result["steps"]}
        assert "prompt_cut" in by_name["title"]["details"]
        assert "prompt_cut" not in (by_name["tags"].get("details") or {})
        assert PROMPT_CUTS.get() is None

    @pytest.mark.asyncio
    async def test_the_preview_shows_it_before_anything_is_written(self, mock_paperless, mock_llm):
        from app.services.steps import (
            CorrespondentStep,
            DocumentTypeStep,
            FieldsStep,
            TagsStep,
            TitleStep,
        )

        processor = _processor(mock_paperless, _title_step(cut=True))
        mock_paperless.get_tags = AsyncMock(return_value=[{"id": 1, "name": "ai-title"}])
        mock_paperless.get_correspondents = AsyncMock(return_value=[])
        mock_paperless.get_document_types = AsyncMock(return_value=[])
        mock_paperless.get_custom_fields = AsyncMock(return_value=[])
        cut_title = _title_step(cut=True).execute
        nothing = AsyncMock(return_value=StepResult(data={}))

        # The preview builds its own steps, so the real classes are what runs.
        with (
            patch("app.services.processor.LLMHandlerManager.get_handler", AsyncMock(return_value=mock_llm)),
            patch.object(TitleStep, "execute", cut_title),
            patch.object(CorrespondentStep, "execute", nothing),
            patch.object(DocumentTypeStep, "execute", nothing),
            patch.object(TagsStep, "execute", nothing),
            patch.object(FieldsStep, "execute", nothing),
        ):
            preview = await processor.process_document_preview(89)

        title = next(s for s in preview["steps"] if s["name"] == "title")
        assert title["details"]["prompt_cut"] == {"evaluated": 2_050, "window": 4_096}
