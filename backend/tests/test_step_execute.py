"""Unit tests for step execute() methods and processor tag-merge logic.

Each test uses mock PaperlessClient + mock LLMHandler + mock DB session.
No real network calls or database access.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# Imports for tasks
from app.services.steps.title_step import TitleStep
from app.services.steps.correspondent_step import CorrespondentStep
from app.services.steps.document_type_step import DocumentTypeStep
from app.services.steps.tags_step import TagsStep
from app.services.steps.fields_step import FieldsStep
from app.services.processor import DocumentProcessor
from app.services.steps.base import StepContext
from app.models import Prompt


@patch("app.database.get_async_session")
class TestTitleStep:
    @pytest.fixture
    def ctx(self, mock_paperless, mock_llm):
        return StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={
                "modular_tag_process": "ai-process",
                "modular_tag_title": "ai-title",
            },
            trigger_tags={"ai-process"},
            ocr_text="This is an Amazon invoice for office supplies.",
        )

    @pytest.fixture
    def mock_get_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_returns_title_from_llm(self, mock_get_session, ctx, mock_llm):
        mock_prompt = MagicMock(spec=Prompt)
        mock_prompt.system_prompt = "You are a title generator."
        mock_prompt.user_template = "Title for: {content}"
        mock_prompt.is_active = True
        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=mock_prompt))
        )
        mock_get_session.return_value.__aenter__.return_value = mock_session

        mock_llm.complete = AsyncMock(
            return_value={
                "text": "Amazon Invoice - Office Supplies",
                "raw": "",
            }
        )

        step = await TitleStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {"title": "Amazon Invoice - Office Supplies"}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_no_content_returns_error(
        self, mock_get_session, mock_paperless, mock_llm
    ):
        empty_paperless = AsyncMock()
        empty_paperless.get_document = AsyncMock(
            return_value={
                "id": 1,
                "title": "",
                "content": None,
                "tags": [],
                "custom_fields": [],
            }
        )
        empty_paperless.get_correspondents = AsyncMock(return_value=[])
        ctx = StepContext(
            doc_id=1,
            paperless=empty_paperless,
            llm=mock_llm,
            config={
                "modular_tag_process": "ai-process",
                "modular_tag_title": "ai-title",
            },
            trigger_tags={"ai-process"},
            ocr_text=None,
        )

        step = await TitleStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {}
        assert result.error == "No content available"

    @pytest.mark.asyncio
    async def test_empty_llm_response_returns_empty(
        self, mock_get_session, ctx, mock_llm
    ):
        mock_prompt = MagicMock(spec=Prompt)
        mock_prompt.system_prompt = "You are a title generator."
        mock_prompt.user_template = "Title for: {content}"
        mock_prompt.is_active = True
        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=mock_prompt))
        )
        mock_get_session.return_value.__aenter__.return_value = mock_session

        mock_llm.complete = AsyncMock(return_value={"text": "", "raw": ""})

        step = await TitleStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_substitutes_correspondents_list(
        self, mock_get_session, ctx, mock_llm, mock_paperless
    ):
        mock_prompt = MagicMock(spec=Prompt)
        mock_prompt.system_prompt = "You are a title generator."
        mock_prompt.user_template = (
            "Title for: {content}\nCorrespondents: {correspondents_list}"
        )
        mock_prompt.is_active = True
        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=mock_prompt))
        )
        mock_get_session.return_value.__aenter__.return_value = mock_session

        mock_llm.complete = AsyncMock(
            return_value={
                "text": "Test Title",
                "raw": "",
            }
        )

        step = await TitleStep.from_config(ctx.config)
        await step.execute(ctx)

        call_kwargs = mock_llm.complete.call_args
        user_prompt = call_kwargs[1]["user_prompt"]
        assert '"Amazon"' in user_prompt
        assert '"BAUHAUS"' in user_prompt


@patch("app.database.get_async_session")
class TestCorrespondentStep:
    @pytest.fixture
    def ctx(self, mock_paperless, mock_llm):
        return StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={
                "modular_tag_process": "ai-process",
                "modular_tag_correspondent": "ai-correspondent",
            },
            trigger_tags={"ai-process"},
            ocr_text="I received a delivery from Amazon today.",
        )

    def _setup_db(self, mock_get_session):
        mock_prompt = MagicMock(spec=Prompt)
        mock_prompt.system_prompt = "You are a correspondent detector."
        mock_prompt.user_template = (
            "Who sent: {content}\nCorrespondents: {correspondents_list}"
        )
        mock_prompt.is_active = True
        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=mock_prompt))
        )
        mock_get_session.return_value.__aenter__.return_value = mock_session

    @pytest.mark.asyncio
    async def test_returns_correspondent_id_on_match(
        self, mock_get_session, ctx, mock_llm
    ):
        """CorrespondentStep returns correspondent ID when LLM name matches."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(return_value={"text": "Amazon", "raw": ""})

        step = await CorrespondentStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {"correspondent": 1}


@patch("app.database.get_async_session")
class TestDocumentTypeStep:
    @pytest.fixture
    def ctx(self, mock_paperless, mock_llm):
        return StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={
                "modular_tag_process": "ai-process",
                "modular_tag_document_type": "ai-document-type",
            },
            trigger_tags={"ai-process"},
            ocr_text="Invoice number 12345 for services rendered.",
        )

    def _setup_db(self, mock_get_session):
        mock_prompt = MagicMock(spec=Prompt)
        mock_prompt.system_prompt = "You are a document type classifier."
        mock_prompt.user_template = "Classify: {content}\nTypes: {document_types_list}"
        mock_prompt.is_active = True
        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=mock_prompt))
        )
        mock_get_session.return_value.__aenter__.return_value = mock_session

    @pytest.mark.asyncio
    async def test_returns_document_type_id_on_match(
        self, mock_get_session, ctx, mock_llm
    ):
        """DocumentTypeStep returns document_type ID when LLM name matches."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(return_value={"text": "Invoice", "raw": ""})

        step = await DocumentTypeStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {"document_type": 1}
        assert ctx.detected_type == "Invoice"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self, mock_get_session, ctx, mock_llm):
        """DocumentTypeStep matches document type case-insensitively."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(return_value={"text": "INVOICE", "raw": ""})

        step = await DocumentTypeStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {"document_type": 1}

    @pytest.mark.asyncio
    async def test_none_response_returns_empty(self, mock_get_session, ctx, mock_llm):
        """DocumentTypeStep returns empty StepResult when LLM returns 'none'."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(return_value={"text": "none", "raw": ""})

        step = await DocumentTypeStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {}

    @pytest.mark.asyncio
    async def test_unknown_type_returns_empty(self, mock_get_session, ctx, mock_llm):
        """DocumentTypeStep returns empty StepResult when LLM returns unknown type."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"text": "UnknownDocType", "raw": ""}
        )

        step = await DocumentTypeStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {}

    @pytest.mark.asyncio
    async def test_unknown_correspondent_returns_empty(
        self, mock_get_session, ctx, mock_llm
    ):
        """CorrespondentStep returns empty StepResult when LLM returns unknown name."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"text": "UnknownCompany", "raw": ""}
        )

        step = await CorrespondentStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {}


@patch("app.database.get_async_session")
class TestTagsStep:
    @pytest.fixture
    def ctx(self, mock_paperless, mock_llm):
        return StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={
                "modular_tag_process": "ai-process",
                "modular_tag_tags": "ai-tags",
                "tag_blacklist": "reviewed",
            },
            trigger_tags={"ai-process"},
            ocr_text="German invoice from Amazon.",
        )

    def _setup_db(self, mock_get_session):
        mock_prompt = MagicMock(spec=Prompt)
        mock_prompt.system_prompt = "You are a tag suggestor."
        mock_prompt.user_template = "Suggest tags: {content}\nTags: {tags_list}"
        mock_prompt.is_active = True
        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=mock_prompt))
        )
        mock_get_session.return_value.__aenter__.return_value = mock_session

    @pytest.mark.asyncio
    async def test_returns_tag_ids_for_valid_names(
        self, mock_get_session, ctx, mock_llm
    ):
        """TagsStep returns tag IDs when LLM returns valid tag names."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={
                "text": "Amazon, inbox",
                "raw": "",
            }
        )

        step = await TagsStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert set(result.data["tags"]) == {1, 6}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_blacklist_filters_tags(self, mock_get_session, ctx, mock_llm):
        """TagsStep skips tags listed in tag_blacklist config."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={
                "text": "Amazon, reviewed",
                "raw": "",
            }
        )

        step = await TagsStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert 10 not in result.data.get("tags", [])

    @pytest.mark.asyncio
    async def test_unknown_tag_names_skipped(self, mock_get_session, ctx, mock_llm):
        """TagsStep silently skips tag names not found in Paperless."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={
                "text": "Amazon, NonExistentTag",
                "raw": "",
            }
        )

        step = await TagsStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data["tags"] == [1]

    @pytest.mark.asyncio
    async def test_none_response_returns_empty(self, mock_get_session, ctx, mock_llm):
        """TagsStep returns empty StepResult when LLM returns 'none'."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(return_value={"text": "none", "raw": ""})

        step = await TagsStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {}

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty(self, mock_get_session, ctx, mock_llm):
        """TagsStep returns empty StepResult when LLM returns empty string."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(return_value={"text": "", "raw": ""})

        step = await TagsStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {}


@patch("app.database.get_async_session")
class TestFieldsStep:
    @pytest.fixture
    def ctx(self, mock_paperless, mock_llm):
        return StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={
                "modular_tag_process": "ai-process",
                "modular_tag_fields": "ai-fields",
            },
            trigger_tags={"ai-process"},
            ocr_text="Invoice INV-123 for $500 dated 2024-01-15.",
        )

    def _setup_db(self, mock_get_session):
        mock_prompt = MagicMock(spec=Prompt)
        mock_prompt.system_prompt = "You are a field extractor."
        mock_prompt.user_template = "Extract: {content}\nFields: {custom_fields_list}"
        mock_prompt.is_active = True
        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=mock_prompt))
        )
        mock_get_session.return_value.__aenter__.return_value = mock_session

    @pytest.mark.asyncio
    async def test_extracts_custom_fields_from_json_response(
        self, mock_get_session, ctx, mock_llm
    ):
        """FieldsStep extracts fields from JSON LLM response and resolves field names to IDs."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={
                "custom_fields": [
                    {"field": "Invoice Number", "value": "INV-123"},
                    {"field": "Amount", "value": "$500"},
                ]
            }
        )

        step = await FieldsStep.from_config(ctx.config)
        result = await step.execute(ctx)

        field_ids = {item["field"] for item in result.data.get("custom_fields", [])}
        assert 1 in field_ids  # Invoice Number id=1
        assert 2 in field_ids  # Amount id=2

    @pytest.mark.asyncio
    async def test_extracts_from_extract_key(self, mock_get_session, ctx, mock_llm):
        """FieldsStep extracts fields from {"extract": {key: value}} JSON structure."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={
                "extract": {
                    "invoice_number": "INV-999",
                    "amount": "$750",
                }
            }
        )

        step = await FieldsStep.from_config(ctx.config)
        result = await step.execute(ctx)

        field_ids = {item["field"] for item in result.data.get("custom_fields", [])}
        assert 1 in field_ids  # Invoice Number
        assert 2 in field_ids  # Amount

    @pytest.mark.asyncio
    async def test_merges_with_existing_document_fields(
        self, mock_get_session, ctx, mock_paperless, mock_llm
    ):
        """FieldsStep merges extracted fields with existing custom field values on the document."""
        self._setup_db(mock_get_session)
        mock_paperless.get_document = AsyncMock(
            return_value={
                "id": 1,
                "title": "",
                "content": "...",
                "tags": [],
                "document_type": None,
                "custom_fields": [
                    {"field": 3, "value": "2024-01-01"}
                ],  # Date already set
            }
        )
        mock_llm.complete = AsyncMock(
            return_value={
                "extract": {"invoice_number": "INV-NEW"},
            }
        )

        step = await FieldsStep.from_config(ctx.config)
        result = await step.execute(ctx)

        fields = {
            item["field"]: item["value"]
            for item in result.data.get("custom_fields", [])
        }
        assert fields.get(1) == "INV-NEW"  # Invoice Number updated
        assert fields.get(3) == "2024-01-01"  # Date preserved

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty(self, mock_get_session, ctx, mock_llm):
        """FieldsStep returns empty StepResult when LLM returns no valid fields."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(return_value={})

        step = await FieldsStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {}


class TestResolveProposedChanges:
    @pytest.mark.asyncio
    async def test_resolves_tags_to_id_name_objects(self):
        """_resolve_proposed_changes converts tag ID list to {id, name} objects."""
        all_tags = [
            {"id": 1, "name": "Amazon"},
            {"id": 6, "name": "inbox"},
        ]
        processor = DocumentProcessor.__new__(DocumentProcessor)
        result = await processor._resolve_proposed_changes(
            {"tags": [1, 6]},
            all_tags,
            [],
            [],
            [],
        )

        assert result["tags"] == [
            {"id": 1, "name": "Amazon"},
            {"id": 6, "name": "inbox"},
        ]

    @pytest.mark.asyncio
    async def test_resolves_unknown_tag_id_to_synthetic_name(self):
        """_resolve_proposed_changes uses tag:N for unknown tag IDs."""
        all_tags = [{"id": 1, "name": "Amazon"}]
        processor = DocumentProcessor.__new__(DocumentProcessor)
        result = await processor._resolve_proposed_changes(
            {"tags": [1, 999]},
            all_tags,
            [],
            [],
            [],
        )

        assert result["tags"][1]["name"] == "tag:999"

    @pytest.mark.asyncio
    async def test_resolves_correspondent_to_id_name_object(self):
        """_resolve_proposed_changes converts correspondent int ID to {id, name}."""
        all_correspondents = [{"id": 3, "name": "HORNBACH"}]
        processor = DocumentProcessor.__new__(DocumentProcessor)
        result = await processor._resolve_proposed_changes(
            {"correspondent": 3},
            [],
            all_correspondents,
            [],
            [],
        )

        assert result["correspondent"] == {"id": 3, "name": "HORNBACH"}

    @pytest.mark.asyncio
    async def test_resolves_document_type_to_id_name_object(self):
        """_resolve_proposed_changes converts document_type int ID to {id, name}."""
        all_document_types = [{"id": 2, "name": "Contract"}]
        processor = DocumentProcessor.__new__(DocumentProcessor)
        result = await processor._resolve_proposed_changes(
            {"document_type": 2},
            [],
            [],
            all_document_types,
            [],
        )

        assert result["document_type"] == {"id": 2, "name": "Contract"}

    @pytest.mark.asyncio
    async def test_resolves_custom_fields_with_names(self):
        """_resolve_proposed_changes converts custom_fields {field} IDs to {id, name, value}."""
        all_custom_fields = [
            {"id": 1, "name": "Invoice Number"},
            {"id": 2, "name": "Amount"},
        ]
        processor = DocumentProcessor.__new__(DocumentProcessor)
        result = await processor._resolve_proposed_changes(
            {
                "custom_fields": [
                    {"field": 1, "value": "INV-123"},
                    {"field": 2, "value": "$500"},
                ]
            },
            [],
            [],
            [],
            all_custom_fields,
        )

        assert result["custom_fields"] == [
            {"id": 1, "name": "Invoice Number", "value": "INV-123"},
            {"id": 2, "name": "Amount", "value": "$500"},
        ]


class TestProcessorTagMerge:
    """Tests for processor tag-merge logic.

    The merge logic is: existing_tag_ids = list(set(doc_tags) | set(tags_from_steps))
    Trigger tag IDs are computed from the document's current tags and removed during finalization.
    """

    def test_tags_step_suggestions_merge_with_existing(self):
        """When TagsStep returns suggested tags, existing doc tags are preserved (union)."""
        doc_tags = [5, 10]  # ai-process, reviewed
        tags_from_steps = [1, 6]  # Amazon, inbox

        existing_tag_ids = list(set(doc_tags) | set(tags_from_steps))
        assert 5 in existing_tag_ids  # original preserved
        assert 10 in existing_tag_ids  # original preserved
        assert 1 in existing_tag_ids  # new added
        assert 6 in existing_tag_ids  # new added

    def test_trigger_tag_ids_computed_from_doc_tags_and_config(self):
        """_get_trigger_tag_ids returns IDs of modular tags present on the document."""
        from app.services.processor import DocumentProcessor, MODULAR_TAG_DEFAULTS

        processor = DocumentProcessor.__new__(DocumentProcessor)
        doc_tag_ids = [5, 9, 10]
        tag_id_to_name = {
            5: "ai-process",
            9: "ai-title",
            10: "Amazon",
            30: "ai-processed",
        }
        config_defaults = dict(MODULAR_TAG_DEFAULTS)

        trigger_ids = processor._get_trigger_tag_ids(
            doc_tag_ids=doc_tag_ids,
            tag_id_to_name=tag_id_to_name,
            config_defaults=config_defaults,
        )

        assert set(trigger_ids) == {5, 9}

    def test_trigger_tag_ids_empty_when_no_modular_tags(self):
        """_get_trigger_tag_ids returns empty list when doc has no modular trigger tags."""
        from app.services.processor import DocumentProcessor, MODULAR_TAG_DEFAULTS

        processor = DocumentProcessor.__new__(DocumentProcessor)
        doc_tag_ids = [10, 20]
        tag_id_to_name = {10: "Amazon", 20: "Invoice"}
        config_defaults = dict(MODULAR_TAG_DEFAULTS)

        trigger_ids = processor._get_trigger_tag_ids(
            doc_tag_ids=doc_tag_ids,
            tag_id_to_name=tag_id_to_name,
            config_defaults=config_defaults,
        )

        assert trigger_ids == []

    def test_add_tags_appends_to_final_list(self):
        """Processed tag (add_tags) is appended to final list."""
        doc_tags = [5]
        tags_from_steps: list[int] = []  # no new tags suggested
        add_tags = [30]  # ai-processed tag to add

        existing_tag_ids = list(set(doc_tags) | set(tags_from_steps))
        for tid in add_tags:
            if tid not in existing_tag_ids:
                existing_tag_ids.append(tid)

        assert 5 in existing_tag_ids  # original preserved
        assert 30 in existing_tag_ids  # processed tag added

    def test_preserves_existing_when_no_steps_suggest_tags(self):
        """When TagsStep returns nothing, existing tags are NOT replaced."""
        doc_tags = [5, 6, 10]  # original doc has process, inbox, reviewed
        tags_from_steps = None  # no tags suggested by any step

        existing_tag_ids = list(doc_tags)
        if tags_from_steps is not None:
            existing_tag_ids = list(set(existing_tag_ids) | set(tags_from_steps))

        # No change — all original tags preserved
        assert existing_tag_ids == [5, 6, 10]


class TestApplyMetadataUpdate:
    """Tests for _apply_metadata_update title truncation."""

    @pytest.mark.asyncio
    async def test_title_truncated_at_128_chars(self, mock_paperless, mock_llm):
        """_apply_metadata_update truncates titles longer than 128 characters."""
        processor = DocumentProcessor(paperless=mock_paperless)
        long_title = "A" * 200  # 200 characters

        await processor._apply_metadata_update(
            doc_id=1,
            title=long_title,
            correspondent_id=None,
            doc_type_id=None,
        )

        call_kwargs = mock_paperless.update_document.call_args[1]
        assert len(call_kwargs["title"]) == 128
        assert call_kwargs["title"] == "A" * 128

    @pytest.mark.asyncio
    async def test_title_under_128_unchanged(self, mock_paperless, mock_llm):
        """_apply_metadata_update passes through titles shorter than 128 characters."""
        processor = DocumentProcessor(paperless=mock_paperless)
        short_title = "Normal Invoice Title"

        await processor._apply_metadata_update(
            doc_id=1,
            title=short_title,
            correspondent_id=None,
            doc_type_id=None,
        )

        call_kwargs = mock_paperless.update_document.call_args[1]
        assert call_kwargs["title"] == "Normal Invoice Title"

    @pytest.mark.asyncio
    async def test_none_title_not_sent(self, mock_paperless, mock_llm):
        """_apply_metadata_update does not send title=None to Paperless."""
        processor = DocumentProcessor(paperless=mock_paperless)

        await processor._apply_metadata_update(
            doc_id=1,
            title=None,
            correspondent_id=None,
            doc_type_id=None,
        )

        mock_paperless.update_document.assert_not_called()
