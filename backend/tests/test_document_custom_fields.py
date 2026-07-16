"""The {document_custom_fields_list} template variable (issue #37).

Resolves to only the custom fields already assigned to the document, so
prompts can be scoped to what the document should actually carry instead of
every field defined in the Paperless instance.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import Prompt
from app.services.steps.base import StepContext
from app.services.steps.fields_step import FieldsStep


def _setup_db(mock_get_session, user_template: str):
    mock_prompt = MagicMock(spec=Prompt)
    mock_prompt.system_prompt = "You are a field extractor."
    mock_prompt.user_template = user_template
    mock_prompt.is_active = True
    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(
        return_value=MagicMock(first=MagicMock(return_value=mock_prompt))
    )
    mock_get_session.return_value.__aenter__.return_value = mock_session


@patch("app.database.get_async_session")
class TestDocumentCustomFieldsList:
    @pytest.fixture
    def ctx(self, mock_paperless, mock_llm):
        mock_paperless.get_custom_fields = AsyncMock(
            return_value=[
                {"id": 1, "name": "Summe"},
                {"id": 2, "name": "Rechnungsnummer"},
                {"id": 3, "name": "IBAN"},
            ]
        )
        mock_paperless.get_document = AsyncMock(
            return_value={
                "id": 1,
                "title": "Receipt",
                "content": "Receipt content.",
                "tags": [5],
                "custom_fields": [{"field": 1, "value": None}],
            }
        )
        return StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={
                "modular_tag_process": "ai-process",
                "modular_tag_fields": "ai-fields",
            },
            trigger_tags={"ai-fields"},
            ocr_text="Receipt total 12,90 EUR.",
        )

    @pytest.mark.asyncio
    async def test_resolves_to_assigned_fields_only(
        self, mock_get_session, ctx, mock_llm
    ):
        _setup_db(mock_get_session, "Fields: {document_custom_fields_list}")
        mock_llm.complete = AsyncMock(return_value={})

        step = await FieldsStep.from_config(ctx.config)
        await step.execute(ctx)

        user_prompt = mock_llm.complete.call_args.kwargs["user_prompt"]
        assert "Summe" in user_prompt
        assert "Rechnungsnummer" not in user_prompt
        assert "IBAN" not in user_prompt

    @pytest.mark.asyncio
    async def test_all_fields_variable_is_unchanged(
        self, mock_get_session, ctx, mock_llm
    ):
        _setup_db(mock_get_session, "Fields: {custom_fields_list}")
        mock_llm.complete = AsyncMock(return_value={})

        step = await FieldsStep.from_config(ctx.config)
        await step.execute(ctx)

        user_prompt = mock_llm.complete.call_args.kwargs["user_prompt"]
        assert "Summe" in user_prompt
        assert "Rechnungsnummer" in user_prompt
        assert "IBAN" in user_prompt

    @pytest.mark.asyncio
    async def test_empty_when_document_has_no_assigned_fields(
        self, mock_get_session, ctx, mock_llm, mock_paperless
    ):
        mock_paperless.get_document = AsyncMock(
            return_value={
                "id": 1,
                "title": "Receipt",
                "content": "Receipt content.",
                "tags": [5],
                "custom_fields": [],
            }
        )
        _setup_db(mock_get_session, "Fields: [{document_custom_fields_list}]")
        mock_llm.complete = AsyncMock(return_value={})

        step = await FieldsStep.from_config(ctx.config)
        await step.execute(ctx)

        user_prompt = mock_llm.complete.call_args.kwargs["user_prompt"]
        assert "Fields: []" in user_prompt
