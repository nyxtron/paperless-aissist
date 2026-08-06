"""Guards against silent data loss in the write path.

Two distinct failure modes, both of which destroy user data in Paperless without
surfacing an error the user can act on:

1. OCR fix truncated the prompt at a hardcoded 10000 chars while the skip guard
   honored the configurable limit — raising the limit meant the shortened LLM
   result overwrote the full document text.
2. The trigger tags were swapped before custom fields and the date were written,
   so a rejected value left the document marked processed and never retried.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import Prompt
from app.services.processor import DocumentProcessor
from app.services.steps.base import StepContext, StepResult
from app.services.steps.ocr_fix_step import OCRFixStep


def _setup_prompt(mock_get_session, user_template: str = "Fix this: {content}"):
    prompt = MagicMock(spec=Prompt)
    prompt.system_prompt = "You fix OCR errors."
    prompt.user_template = user_template
    prompt.is_active = True
    session = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=prompt)))
    mock_get_session.return_value.__aenter__.return_value = session


@patch("app.database.get_async_session")
class TestOCRFixTruncation:
    @pytest.mark.asyncio
    async def test_prompt_is_not_truncated_below_the_configured_limit(
        self, mock_get_session, mock_paperless, mock_llm
    ):
        """A raised limit must reach the LLM — otherwise the reply overwrites full text."""
        _setup_prompt(mock_get_session)
        text = "A" * 15000
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"ocr_post_process": "true", "ocr_fix_max_chars": "20000"},
            trigger_tags={"ai-ocr-fix"},
            ocr_text=text,
        )
        mock_llm.complete = AsyncMock(return_value={"text": "fixed"})

        step = await OCRFixStep.from_config(ctx.config)
        await step.execute(ctx)

        sent = mock_llm.complete.call_args.kwargs["user_prompt"]
        assert sent.count("A") == 15000, (
            f"prompt carried {sent.count('A')} of 15000 chars — the reply would "
            "overwrite the document with a shortened version"
        )

    @pytest.mark.asyncio
    async def test_short_llm_reply_is_not_written_back(
        self, mock_get_session, mock_paperless, mock_llm
    ):
        """A reply far shorter than the input is a summary, not a correction.

        Real numbers from a live run: 11690 chars of document text into
        qwen2.5:7b came back as 5436 chars. Writing that back destroys more than
        half the document, which is exactly what the length guard promises to
        prevent.
        """
        _setup_prompt(mock_get_session)
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"ocr_post_process": "true", "ocr_fix_max_chars": "13000"},
            trigger_tags={"ai-ocr-fix"},
            ocr_text="A" * 11690,
        )
        mock_llm.complete = AsyncMock(return_value={"text": "B" * 5436})

        step = await OCRFixStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.skipped is True
        assert result.details["reason"] == "result_too_short"
        assert result.data.get("text") is None
        assert ctx.ocr_text == "A" * 11690, "original text must survive"

    @pytest.mark.asyncio
    async def test_comparable_length_reply_is_accepted(
        self, mock_get_session, mock_paperless, mock_llm
    ):
        """A genuine correction keeps roughly the same length and is written."""
        _setup_prompt(mock_get_session)
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"ocr_post_process": "true", "ocr_fix_max_chars": "13000"},
            trigger_tags={"ai-ocr-fix"},
            ocr_text="A" * 11690,
        )
        mock_llm.complete = AsyncMock(return_value={"text": "B" * 11500})

        step = await OCRFixStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.skipped is False
        assert result.data["text"] == "B" * 11500

    @pytest.mark.asyncio
    async def test_default_limit_still_truncates_at_ten_thousand(
        self, mock_get_session, mock_paperless, mock_llm
    ):
        """With the default limit the guard skips first, so nothing is truncated."""
        _setup_prompt(mock_get_session)
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"ocr_post_process": "true", "ocr_fix_max_chars": "10000"},
            trigger_tags={"ai-ocr-fix"},
            ocr_text="A" * 15000,
        )
        mock_llm.complete = AsyncMock(return_value={"text": "fixed"})

        step = await OCRFixStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.skipped is True
        assert result.details["reason"] == "content_too_large"
        mock_llm.complete.assert_not_awaited()


class TestTagSwapIsTheCommitPoint:
    def _processor(self, mock_paperless, step_data: dict):
        step = MagicMock()
        step.name = "fields"
        step.can_handle.return_value = True
        step.execute = AsyncMock(return_value=StepResult(data=step_data))
        step.update_metadata = AsyncMock()

        processor = DocumentProcessor(paperless=mock_paperless)
        processor._build_steps = AsyncMock(return_value=[step])
        processor._get_config_dict = AsyncMock(
            return_value={"modular_tag_process": "ai-process"}
        )
        processor._get_config = AsyncMock(
            side_effect=lambda key, default=None: {
                "process_tag": "ai-process",
                "processed_tag": "ai-processed",
            }.get(key, default)
        )
        processor._log_processing = AsyncMock(return_value=123)
        processor._apply_metadata_update = AsyncMock()
        processor._apply_tag_updates = AsyncMock()
        return processor

    @pytest.mark.asyncio
    async def test_tags_are_not_swapped_when_custom_fields_are_rejected(
        self, mock_paperless, mock_llm
    ):
        """A rejected field value must leave the trigger tags in place for a retry."""
        mock_llm.provider = "test-provider"
        mock_llm.model = "test-model"
        mock_paperless.update_document = AsyncMock(
            side_effect=Exception('{"custom_fields":["Invalid value"]}')
        )

        processor = self._processor(
            mock_paperless, {"custom_fields": [{"field": 1, "value": "bad"}]}
        )

        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            result = await processor.process_document(1)

        assert result["success"] is False
        processor._apply_tag_updates.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_custom_fields_are_written_before_the_tag_swap(
        self, mock_paperless, mock_llm
    ):
        """On success the tag swap must come last, so it commits completed work."""
        mock_llm.provider = "test-provider"
        mock_llm.model = "test-model"
        order: list[str] = []
        mock_paperless.update_document = AsyncMock(
            side_effect=lambda *a, **kw: order.append("fields")
        )

        processor = self._processor(
            mock_paperless, {"custom_fields": [{"field": 1, "value": "ok"}]}
        )
        processor._apply_tag_updates = AsyncMock(
            side_effect=lambda *a, **kw: order.append("tags")
        )

        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            result = await processor.process_document(1)

        assert result["success"] is True
        assert order == ["fields", "tags"], f"write order was {order}"
