"""An unreachable provider must not cost a document its run (issue #41).

The processor has a handler that drops the log entry and reports the run as
retryable, but every step ran inside a broad ``except Exception`` that caught
LLMUnavailableError first, so the handler could never fire for a step failure.
The date step and custom field extraction added a second layer of the same:
date filed the outage as a bad reply, fields swallowed it and reported success
with nothing extracted -- which is why LM Studio users saw no error for years.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import LLMUnavailableError
from app.models import Prompt
from app.services.processor import DocumentProcessor
from app.services.steps.base import StepContext, StepResult
from app.services.steps.date_step import DateStep
from app.services.steps.fields_step import FieldsStep


def _prompt_session(**attrs):
    prompt = MagicMock(spec=Prompt)
    prompt.system_prompt = "s"
    prompt.user_template = "{content}"
    prompt.is_active = True
    for key, value in attrs.items():
        setattr(prompt, key, value)
    session = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=prompt)))
    return session


class TestProcessorReportsOutageAsRetryable:
    def _processor(self, mock_paperless, step):
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
        processor._delete_log = AsyncMock()
        processor._apply_metadata_update = AsyncMock()
        processor._apply_tag_updates = AsyncMock()
        return processor

    def _failing_step(self, error: Exception):
        step = MagicMock()
        step.name = "date"
        step.can_handle.return_value = True
        step.execute = AsyncMock(side_effect=error)
        step.update_metadata = AsyncMock()
        return step

    @pytest.mark.asyncio
    async def test_outage_during_a_step_is_retryable(self, mock_paperless, mock_llm):
        mock_llm.provider = "test-provider"
        mock_llm.model = "test-model"
        processor = self._processor(
            mock_paperless, self._failing_step(LLMUnavailableError("LM Studio down"))
        )

        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            result = await processor.process_document(1)

        assert result["success"] is False
        assert result["retryable"] is True
        # The run left no permanent failure behind, and the trigger tag stays put.
        processor._delete_log.assert_awaited()
        processor._apply_tag_updates.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_ordinary_step_error_stays_a_failure(self, mock_paperless, mock_llm):
        """Only outages are retryable — a genuine defect must still be recorded."""
        mock_llm.provider = "test-provider"
        mock_llm.model = "test-model"
        processor = self._processor(
            mock_paperless, self._failing_step(ValueError("bad prompt template"))
        )

        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            result = await processor.process_document(1)

        assert result["success"] is False
        assert result.get("retryable") is not True
        processor._delete_log.assert_not_awaited()


class TestStepsLetTheOutageThrough:
    @pytest.mark.asyncio
    async def test_date_step_does_not_file_an_outage_as_a_bad_reply(
        self, mock_paperless, mock_llm
    ):
        mock_paperless.get_document = AsyncMock(
            return_value={"id": 1, "title": "R", "content": "Rechnung", "created": ""}
        )
        mock_llm.complete = AsyncMock(side_effect=LLMUnavailableError("down"))
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"modular_tag_date": "ai-date"},
            trigger_tags={"ai-date"},
            ocr_text="Rechnungsdatum: 17.03.2026",
        )

        with patch("app.services.steps.date_step.get_async_session") as get_session:
            get_session.return_value.__aenter__.return_value = _prompt_session()
            with pytest.raises(LLMUnavailableError):
                await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

    @pytest.mark.asyncio
    async def test_date_step_rejects_a_reply_that_is_not_an_object(
        self, mock_paperless, mock_llm
    ):
        """A list reply used to raise AttributeError deep inside the step."""
        mock_paperless.get_document = AsyncMock(
            return_value={"id": 1, "title": "R", "content": "Rechnung", "created": ""}
        )
        mock_llm.complete = AsyncMock(return_value=[{"created_date": "2026-03-17"}])
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"modular_tag_date": "ai-date"},
            trigger_tags={"ai-date"},
            ocr_text="Rechnungsdatum: 17.03.2026",
        )

        with patch("app.services.steps.date_step.get_async_session") as get_session:
            get_session.return_value.__aenter__.return_value = _prompt_session()
            result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert isinstance(result, StepResult)
        assert result.error is not None
        assert result.data == {}

    @pytest.mark.asyncio
    async def test_fields_step_does_not_report_an_outage_as_no_fields(
        self, mock_paperless, mock_llm
    ):
        mock_paperless.get_custom_fields = AsyncMock(
            return_value=[{"id": 7, "name": "rechnungsbetrag"}]
        )
        mock_paperless.get_document = AsyncMock(
            return_value={"id": 1, "title": "R", "content": "x", "tags": [], "custom_fields": []}
        )
        mock_llm.complete = AsyncMock(side_effect=LLMUnavailableError("down"))
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"modular_tag_fields": "ai-fields"},
            trigger_tags={"ai-fields"},
            ocr_text="Rechnungsbetrag EUR84.99",
        )

        with patch("app.database.get_async_session") as get_session:
            get_session.return_value.__aenter__.return_value = _prompt_session()
            step = await FieldsStep.from_config(ctx.config)
            with pytest.raises(LLMUnavailableError):
                await step.execute(ctx)

    @pytest.mark.asyncio
    async def test_the_type_specific_prompt_lets_the_outage_through_too(
        self, mock_paperless, mock_llm
    ):
        """The second prompt in the step carries the same guard as the first."""
        mock_paperless.get_custom_fields = AsyncMock(
            return_value=[{"id": 7, "name": "rechnungsbetrag"}]
        )
        mock_paperless.get_document = AsyncMock(
            return_value={"id": 1, "title": "R", "content": "x", "tags": [], "custom_fields": []}
        )
        mock_llm.complete = AsyncMock(side_effect=LLMUnavailableError("down"))
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"modular_tag_fields": "ai-fields"},
            trigger_tags={"ai-fields"},
            ocr_text="Rechnungsbetrag EUR84.99",
            detected_type="Rechnung",
        )

        prompt = MagicMock(spec=Prompt)
        prompt.system_prompt = "s"
        prompt.user_template = "{content}"
        prompt.is_active = True
        session = AsyncMock()
        # No extract prompt, so only the type_specific one reaches the model.
        session.exec = AsyncMock(
            side_effect=[
                MagicMock(first=MagicMock(return_value=None)),
                MagicMock(first=MagicMock(return_value=prompt)),
            ]
        )

        with patch("app.database.get_async_session") as get_session:
            get_session.return_value.__aenter__.return_value = session
            step = await FieldsStep.from_config(ctx.config)
            with pytest.raises(LLMUnavailableError):
                await step.execute(ctx)
