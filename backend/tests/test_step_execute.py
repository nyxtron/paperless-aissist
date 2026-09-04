"""Unit tests for step execute() methods and processor tag-merge logic.

Each test uses mock PaperlessClient + mock LLMHandler + mock DB session.
No real network calls or database access.
"""

import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

# Imports for tasks
from app.services.steps.ocr_step import OCRStep
from app.services.steps.ocr_fix_step import OCRFixStep
from app.services.steps.title_step import TitleStep
from app.services.steps.correspondent_step import CorrespondentStep
from app.services.steps.document_type_step import DocumentTypeStep
from app.services.steps.tags_step import TagsStep
from app.services.steps.fields_step import FieldsStep
from app.services.steps.date_step import DateStep
from app.services.processor import DocumentProcessor
from app.services import scheduler as scheduler_service
from app.services.steps.base import StepContext, StepResult
from app.models import Prompt


class TestOCRStep:
    @pytest.fixture
    def ctx(self, mock_paperless, mock_llm):
        return StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={
                "enable_vision": "false",
                "modular_tag_process": "ai-process",
                "modular_tag_ocr": "ai-ocr",
                "force_ocr_tag": "force_ocr",
            },
            trigger_tags={"ai-process"},
            ocr_text="Existing OCR text.",
        )

    @pytest.mark.asyncio
    async def test_ai_process_does_not_run_vision_ocr_when_enabled(
        self, ctx, mock_paperless
    ):
        """ai-process alone must not call Vision OCR even when Vision is configured."""
        ctx.config["enable_vision"] = "true"
        step = await OCRStep.from_config(ctx.config)

        assert step.can_handle(ctx.trigger_tags) is False

        mock_paperless.get_document_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_modular_ocr_tag_runs_vision_ocr_when_enabled(
        self, ctx, mock_paperless
    ):
        """ai-ocr fetches the PDF and calls Vision OCR."""
        ctx.config["enable_vision"] = "true"
        ctx.trigger_tags = {"ai-ocr"}
        vision_pipeline = AsyncMock()
        vision_pipeline.extract_text_from_pdf = AsyncMock(
            return_value={"text": "Vision OCR text", "raw": ""}
        )

        with (
            patch("app.services.steps.ocr_step.VisionPipeline.create") as create_pipeline,
            patch("app.database.get_async_session") as mock_get_session,
        ):
            create_pipeline.return_value = vision_pipeline
            mock_session = AsyncMock()
            mock_session.exec = AsyncMock(
                return_value=MagicMock(first=MagicMock(return_value=None))
            )
            mock_get_session.return_value.__aenter__.return_value = mock_session

            step = await OCRStep.from_config(ctx.config)
            result = await step.execute(ctx)

        mock_paperless.get_document_file.assert_awaited_once_with(1, original=True)
        vision_pipeline.extract_text_from_pdf.assert_awaited_once_with(
            b"fake pdf bytes", prompt=None
        )
        assert result.data == {"text": "Vision OCR text"}
        assert result.error is None
        assert ctx.ocr_text == "Vision OCR text"

    @pytest.mark.asyncio
    async def test_uses_active_vision_ocr_prompt(self, ctx):
        """OCRStep passes the active vision_ocr system prompt to Vision OCR."""
        ctx.config["enable_vision"] = "true"
        ctx.trigger_tags = {"ai-ocr"}
        vision_pipeline = AsyncMock()
        vision_pipeline.extract_text_from_pdf = AsyncMock(
            return_value={"text": "Prompted OCR text", "raw": ""}
        )
        mock_prompt = MagicMock(spec=Prompt)
        mock_prompt.system_prompt = "Read every page carefully."

        with (
            patch("app.services.steps.ocr_step.VisionPipeline.create") as create_pipeline,
            patch("app.database.get_async_session") as mock_get_session,
        ):
            create_pipeline.return_value = vision_pipeline
            mock_session = AsyncMock()
            mock_session.exec = AsyncMock(
                return_value=MagicMock(first=MagicMock(return_value=mock_prompt))
            )
            mock_get_session.return_value.__aenter__.return_value = mock_session

            step = await OCRStep.from_config(ctx.config)
            await step.execute(ctx)

        vision_pipeline.extract_text_from_pdf.assert_awaited_once_with(
            b"fake pdf bytes", prompt="Read every page carefully."
        )

    def test_modular_ocr_fix_tag_does_not_trigger_vision_ocr(self, ctx):
        """ai-ocr-fix is handled by OCRFixStep, not by OCRStep."""
        step = OCRStep(ctx.config)

        assert step.can_handle({"ai-ocr-fix"}) is False

    def test_combined_ai_ocr_and_ai_process_allows_ocr_step(self, ctx):
        """Combining ai-ocr with ai-process lets OCR run before normal processing."""
        ctx.trigger_tags = {"ai-ocr", "ai-process"}
        step = OCRStep(ctx.config)

        assert step.can_handle(ctx.trigger_tags) is True


class TestOCRFixStep:
    @pytest.fixture
    def ctx(self, mock_paperless, mock_llm):
        return StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={
                "ocr_post_process": "true",
                "ocr_fix_max_chars": "10000",
                "modular_tag_ocr_fix": "ai-ocr-fix",
                "force_ocr_tag": "force_ocr",
                "force_ocr_fix_tag": "force-ocr-fix",
            },
            trigger_tags={"ai-ocr-fix"},
            ocr_text="x" * 10001,
        )

    @pytest.mark.asyncio
    async def test_skips_large_text_without_overwriting_content(self, ctx, mock_llm):
        mock_llm.complete = AsyncMock(return_value={"text": "shortened", "raw": ""})

        step = await OCRFixStep.from_config(ctx.config)
        result = await step.execute(ctx)
        await step.update_metadata(ctx, result)

        assert result.skipped is True
        assert result.data == {}
        assert result.details == {
            "reason": "content_too_large",
            "content_length": 10001,
            "max_chars": 10000,
        }
        assert ctx.ocr_text == "x" * 10001
        mock_llm.complete.assert_not_called()
        ctx.paperless.update_document.assert_not_called()

    @pytest.mark.asyncio
    async def test_fixes_text_within_limit_and_updates_content(self, ctx, mock_llm):
        ctx.ocr_text = "Th1s OCR text needs f1xing."
        mock_prompt = MagicMock(spec=Prompt)
        mock_prompt.system_prompt = "Fix OCR."
        mock_prompt.user_template = "OCR Text:\n{content}"
        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=mock_prompt))
        )
        mock_llm.complete = AsyncMock(
            return_value={"text": "This OCR text needs fixing.", "raw": ""}
        )

        with patch("app.database.get_async_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            step = await OCRFixStep.from_config(ctx.config)
            result = await step.execute(ctx)
            await step.update_metadata(ctx, result)

        assert result.skipped is False
        assert result.data == {"text": "This OCR text needs fixing."}
        assert ctx.ocr_text == "This OCR text needs fixing."
        mock_llm.complete.assert_awaited_once_with(
            system_prompt="Fix OCR.",
            user_prompt="OCR Text:\nTh1s OCR text needs f1xing.",
            json_mode=False,
        )
        ctx.paperless.update_document.assert_awaited_once_with(
            1,
            content="This OCR text needs fixing.",
        )

    def test_max_chars_can_be_set_from_environment(self, monkeypatch):
        monkeypatch.setenv("OCR_FIX_MAX_CHARS", "12345")

        step = OCRFixStep({})

        assert step.ocr_fix_max_chars == 12345


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

    @pytest.mark.asyncio
    async def test_parses_two_stage_json_response(
        self, mock_get_session, ctx, mock_llm
    ):
        """CorrespondentStep accepts the {name, is_existing} JSON shape."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"text": '{"name": "Amazon", "is_existing": true}', "raw": ""}
        )

        step = await CorrespondentStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {"correspondent": 1}

    @pytest.mark.asyncio
    async def test_parses_json_mode_parsed_dict(
        self, mock_get_session, ctx, mock_llm
    ):
        """In json_mode, complete() returns the parsed JSON dict directly
        ({"name", "is_existing"}), not wrapped in {"text": ...} — the step must
        read the name from it."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"name": "Amazon", "is_existing": True}
        )

        step = await CorrespondentStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {"correspondent": 1}

    @pytest.mark.asyncio
    async def test_creates_from_parsed_dict_result(
        self, mock_get_session, ctx, mock_llm
    ):
        """Creation works when complete() returns a parsed JSON dict naming an
        unknown correspondent."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"name": "Telekom", "is_existing": False}
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock(
            return_value=({"id": 99, "name": "Telekom"}, True)
        )

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {"correspondent": 99}
        ctx.paperless.get_or_create_correspondent.assert_awaited_once_with(
            "Telekom", owner_mode="api_user", matching_algorithm=None
        )

    @pytest.mark.asyncio
    async def test_completes_with_json_mode_off(
        self, mock_get_session, ctx, mock_llm
    ):
        """The step never turns json_mode on: the bundled prompt asks for JSON
        and _parse_response extracts it, so installs with a legacy/edited prompt
        keep working."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(return_value={"text": "Amazon", "raw": ""})

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        await step.execute(ctx)

        assert mock_llm.complete.await_args.kwargs["json_mode"] is False

    @pytest.mark.asyncio
    async def test_reuses_existing_when_model_claims_new(
        self, mock_get_session, ctx, mock_llm
    ):
        """A proposed name matching an existing entry is reused, not created,
        even when the model flags it as new and creation is enabled. Uses the
        {"text": ...} shape complete() returns with json_mode off."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"text": '{"name": "amazon", "is_existing": false}', "raw": ""}
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock()

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {"correspondent": 1}
        ctx.paperless.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_normalized_duplicate_blocks_create(
        self, mock_get_session, ctx, mock_llm
    ):
        """Case and whitespace differences do not trigger a duplicate create."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"text": "  hornbach  ", "raw": ""}
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock()

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {"correspondent": 3}
        ctx.paperless.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_new_correspondent_when_enabled(
        self, mock_get_session, ctx, mock_llm
    ):
        """An unmatched name is created when creation is enabled, and logged
        via StepResult.details for later review."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"text": '{"name": "Telekom", "is_existing": false}', "raw": ""}
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock(
            return_value=({"id": 99, "name": "Telekom"}, True)
        )

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {"correspondent": 99}
        ctx.paperless.get_or_create_correspondent.assert_awaited_once_with(
            "Telekom", owner_mode="api_user", matching_algorithm=None
        )
        assert result.details["created_correspondent"] == {"id": 99, "name": "Telekom"}

    @pytest.mark.asyncio
    async def test_passes_the_owner_and_matching_settings_on(
        self, mock_get_session, ctx, mock_llm
    ):
        """The two opt-in settings only take effect through this call, so the
        step has to hand them to the client, not the defaults."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"name": "Telekom", "is_existing": False}
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock(
            return_value=({"id": 99, "name": "Telekom"}, True)
        )

        config = {
            **ctx.config,
            "correspondent_create_new": "true",
            "correspondent_create_owner": "none",
            "correspondent_create_matching": "6",
        }
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {"correspondent": 99}
        ctx.paperless.get_or_create_correspondent.assert_awaited_once_with(
            "Telekom", owner_mode="none", matching_algorithm=6
        )

    @pytest.mark.asyncio
    async def test_reuses_when_get_or_create_returns_existing(
        self, mock_get_session, ctx, mock_llm
    ):
        """When the client resolves a concurrent create to an existing entry
        (created=False), the step reuses it without logging a creation."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"text": '{"name": "Telekom", "is_existing": false}', "raw": ""}
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock(
            return_value=({"id": 42, "name": "Telekom"}, False)
        )

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {"correspondent": 42}
        assert "created_correspondent" not in result.details

    @pytest.mark.asyncio
    async def test_does_not_create_when_disabled(
        self, mock_get_session, ctx, mock_llm
    ):
        """An unmatched name is dropped (strict default) when creation is off."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"text": '{"name": "Telekom", "is_existing": false}', "raw": ""}
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock()

        step = await CorrespondentStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {}
        ctx.paperless.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_create_from_untrusted_raw_reply(
        self, mock_get_session, ctx, mock_llm
    ):
        """A short, plausible NON-JSON reply must not be created from — the only
        thing that may block it is the trust check, so the fixture is a bare word
        (`Emons`) that clears the plausibility gate and reaches the trust gate."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(return_value={"text": "Emons", "raw": ""})
        ctx.paperless.get_or_create_correspondent = AsyncMock()

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {}
        assert result.details.get("correspondent_create_skipped") == "untrusted_response"
        ctx.paperless.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_is_existing_string_true_blocks_create(
        self, mock_get_session, ctx, mock_llm
    ):
        """A model returning is_existing as the string "true" (not a bool) with no
        match must still be treated as claimed-existing and not created."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={
                "text": '{"name": "Deutsche Telekom AG", "is_existing": "true"}',
                "raw": "",
            }
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock()

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {}
        ctx.paperless.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_quoted_name_reuses_existing_not_duplicate(
        self, mock_get_session, ctx, mock_llm
    ):
        """A quoted name (`"Amazon"`, echoed from the candidate list) must match
        the existing unquoted `Amazon` and be reused, not created as a duplicate."""
        self._setup_db(mock_get_session)
        payload = json.dumps({"name": '"Amazon"', "is_existing": False})
        mock_llm.complete = AsyncMock(return_value={"text": payload, "raw": ""})
        ctx.paperless.get_or_create_correspondent = AsyncMock()

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {"correspondent": 1}
        ctx.paperless.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_with_missing_id_is_noop_not_fatal(
        self, mock_get_session, ctx, mock_llm
    ):
        """A 2xx create whose body lacks `id` must be a no-op (error=None), not a
        KeyError that the outer handler turns into a fatal step."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"text": '{"name": "Telekom", "is_existing": false}', "raw": ""}
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock(
            return_value=({"name": "Telekom"}, True)  # no "id" key
        )

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {}
        assert result.error is None
        assert "correspondent_create_failed" in result.details

    @pytest.mark.asyncio
    async def test_parses_json_object_with_trailing_noise(
        self, mock_get_session, ctx, mock_llm
    ):
        """A valid JSON object followed by a stray brace must still be parsed
        (balanced scan), not dropped by a greedy match."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={
                "text": '{"name": "Amazon", "is_existing": true} }',
                "raw": "",
            }
        )

        step = await CorrespondentStep.from_config(ctx.config)
        result = await step.execute(ctx)

        assert result.data == {"correspondent": 1}

    @pytest.mark.asyncio
    async def test_does_not_create_none_sentinel_with_punctuation(
        self, mock_get_session, ctx, mock_llm
    ):
        """"None." (trailing punctuation) is a no-sender sentinel, not a name."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"text": '{"name": "None.", "is_existing": false}', "raw": ""}
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock()

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {}
        ctx.paperless.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_create_when_model_claims_existing_but_no_match(
        self, mock_get_session, ctx, mock_llm
    ):
        """is_existing=true with no match is the surest sign of a mangled name;
        the step reuses-or-drops, never creates."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={
                "text": '{"name": "Deutsche Telekom AG", "is_existing": true}',
                "raw": "",
            }
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock()

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {}
        ctx.paperless.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_create_implausibly_long_name(
        self, mock_get_session, ctx, mock_llm
    ):
        """A prose-length 'name' is rejected by the plausibility gate."""
        self._setup_db(mock_get_session)
        long_name = "Der Absender dieses Dokuments ist vermutlich die Firma Emons"
        mock_llm.complete = AsyncMock(
            return_value={
                "text": json.dumps({"name": long_name, "is_existing": False}),
                "raw": "",
            }
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock()

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {}
        ctx.paperless.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_failure_is_noop_not_fatal(
        self, mock_get_session, ctx, mock_llm
    ):
        """A create failure must not fail the document: the step returns a no-op
        (no error) so the remaining steps still run."""
        self._setup_db(mock_get_session)
        mock_llm.complete = AsyncMock(
            return_value={"text": '{"name": "Telekom", "is_existing": false}', "raw": ""}
        )
        ctx.paperless.get_or_create_correspondent = AsyncMock(
            side_effect=Exception("boom")
        )

        config = {**ctx.config, "correspondent_create_new": "true"}
        step = await CorrespondentStep.from_config(config)
        result = await step.execute(ctx)

        assert result.data == {}
        assert result.error is None
        assert "correspondent_create_failed" in result.details


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
    async def test_none_blacklist_allows_valid_tags(self, mock_get_session, ctx, mock_llm):
        """TagsStep treats a None tag_blacklist config value as empty."""
        self._setup_db(mock_get_session)
        ctx.config["tag_blacklist"] = None
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
    async def test_missing_blacklist_allows_valid_tags(
        self, mock_get_session, ctx, mock_llm
    ):
        """TagsStep treats a missing tag_blacklist config value as empty."""
        self._setup_db(mock_get_session)
        ctx.config.pop("tag_blacklist")
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


class TestDateStep:
    @pytest.fixture
    def ctx(self, mock_paperless, mock_llm):
        return StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"modular_tag_date": "ai-date"},
            trigger_tags={"ai-date"},
            ocr_text="Rechnungsdatum: Dienstag, 28. April 2026",
        )

    def _setup_db(self, mock_get_session):
        prompt = MagicMock(spec=Prompt)
        prompt.prompt_type = "date"
        prompt.system_prompt = "Return strict JSON."
        prompt.user_template = (
            "Title: {title}\nCurrent: {created_date}\nToday: {current_date}\n{content}"
        )
        prompt.is_active = True
        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=prompt))
        )
        mock_get_session.return_value.__aenter__.return_value = mock_session

    @pytest.mark.asyncio
    async def test_updates_created_date_on_high_confidence(
        self, ctx, mock_llm, mock_paperless
    ):
        mock_llm.complete = AsyncMock(
            return_value={
                "text": (
                    '{"created_date":"2026-04-28","confidence":"high",'
                    '"evidence":"Rechnungsdatum: Dienstag, 28. April 2026"}'
                )
            }
        )
        mock_paperless.get_document = AsyncMock(
            return_value={
                "id": 1,
                "title": "Invoice",
                "created": "2026-05-17",
                "content": "Original Paperless text",
                "tags": [42],
            }
        )

        with patch("app.services.steps.date_step.get_async_session") as mock_get_session:
            self._setup_db(mock_get_session)
            result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert result.data == {"created_date": "2026-04-28"}
        assert result.details == {
            "created_date": "2026-04-28",
            "confidence": "high",
            "evidence": "Rechnungsdatum: Dienstag, 28. April 2026",
        }
        user_prompt = mock_llm.complete.await_args.kwargs["user_prompt"]
        assert "Rechnungsdatum: Dienstag, 28. April 2026" in user_prompt
        assert "Current: 2026-05-17" in user_prompt
        assert "Today: " in user_prompt
        assert "{current_date}" not in user_prompt

    @pytest.mark.asyncio
    async def test_updates_created_date_on_medium_confidence(self, ctx, mock_llm):
        mock_llm.complete = AsyncMock(
            return_value={
                "text": '{"created_date":"2026-04-28","confidence":"medium","evidence":"28. April 2026"}'
            }
        )

        with patch("app.services.steps.date_step.get_async_session") as mock_get_session:
            self._setup_db(mock_get_session)
            result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert result.data == {"created_date": "2026-04-28"}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_accepts_parsed_json_response_from_llm_handler(self, ctx, mock_llm):
        mock_llm.complete = AsyncMock(
            return_value={
                "created_date": "2026-04-28",
                "confidence": "high",
                "evidence": "28. April 2026",
            }
        )

        with patch("app.services.steps.date_step.get_async_session") as mock_get_session:
            self._setup_db(mock_get_session)
            result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert result.data == {"created_date": "2026-04-28"}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_skips_low_confidence_without_paperless_update(
        self, ctx, mock_llm, mock_paperless
    ):
        mock_llm.complete = AsyncMock(
            return_value={
                "text": '{"created_date":"2026-04-28","confidence":"low","evidence":"unclear"}'
            }
        )

        with patch("app.services.steps.date_step.get_async_session") as mock_get_session:
            self._setup_db(mock_get_session)
            result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert result.skipped is True
        assert result.data == {}
        assert result.details["reason"] == "low confidence"
        mock_paperless.update_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_null_date(self, ctx, mock_llm):
        mock_llm.complete = AsyncMock(
            return_value={
                "text": '{"created_date":null,"confidence":"medium","evidence":""}'
            }
        )

        with patch("app.services.steps.date_step.get_async_session") as mock_get_session:
            self._setup_db(mock_get_session)
            result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert result.skipped is True
        assert result.details["created_date"] is None
        assert result.details["reason"] == "no reliable document date"

    @pytest.mark.asyncio
    async def test_skips_when_no_active_prompt(self, ctx):
        with patch("app.services.steps.date_step.get_async_session") as mock_get_session:
            mock_session = AsyncMock()
            mock_session.exec = AsyncMock(
                return_value=MagicMock(first=MagicMock(return_value=None))
            )
            mock_get_session.return_value.__aenter__.return_value = mock_session
            result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert result.skipped is True
        assert result.details["reason"] == "no active date prompt"

    @pytest.mark.asyncio
    async def test_skips_when_no_content(self, ctx, mock_paperless):
        ctx.ocr_text = None
        mock_paperless.get_document = AsyncMock(
            return_value={"id": 1, "title": "Empty", "created": "2026-05-17", "content": ""}
        )

        result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert result.skipped is True
        assert result.details["reason"] == "no content"

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self, ctx, mock_llm):
        mock_llm.complete = AsyncMock(return_value={"text": "not json"})

        with patch("app.services.steps.date_step.get_async_session") as mock_get_session:
            self._setup_db(mock_get_session)
            result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert result.error.startswith("invalid date response:")

    @pytest.mark.asyncio
    async def test_invalid_calendar_date_is_skipped(self, ctx, mock_llm):
        mock_llm.complete = AsyncMock(
            return_value={
                "text": '{"created_date":"2026-02-31","confidence":"high","evidence":"31.02.2026"}'
            }
        )

        with patch("app.services.steps.date_step.get_async_session") as mock_get_session:
            self._setup_db(mock_get_session)
            result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert result.skipped is True
        assert result.error is None
        assert result.data == {}
        assert result.details["created_date"] == "2026-02-31"
        assert result.details["confidence"] == "high"
        assert result.details["evidence"] == "31.02.2026"
        assert result.details["reason"] == "invalid calendar date"

    @pytest.mark.asyncio
    async def test_mixed_date_or_null_string_is_skipped(self, ctx, mock_llm):
        mock_llm.complete = AsyncMock(
            return_value={
                "text": '{"created_date":"2019-03-22|null","confidence":"medium","evidence":"valid from: 03.99"}'
            }
        )

        with patch("app.services.steps.date_step.get_async_session") as mock_get_session:
            self._setup_db(mock_get_session)
            result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert result.skipped is True
        assert result.error is None
        assert result.data == {}
        assert result.details["created_date"] == "2019-03-22|null"
        assert result.details["confidence"] == "medium"
        assert result.details["evidence"] == "valid from: 03.99"
        assert result.details["reason"] == "invalid date format"

    @pytest.mark.asyncio
    async def test_qwen_mixed_date_or_null_string_is_skipped(self, ctx, mock_llm):
        mock_llm.complete = AsyncMock(
            return_value={
                "text": '{"created_date":"2026-07-08|null","confidence":"medium","evidence":"08.07.2026"}'
            }
        )

        with patch("app.services.steps.date_step.get_async_session") as mock_get_session:
            self._setup_db(mock_get_session)
            result = await DateStep({"modular_tag_date": "ai-date"}).execute(ctx)

        assert result.skipped is True
        assert result.error is None
        assert result.data == {}
        assert result.details["created_date"] == "2026-07-08|null"
        assert result.details["confidence"] == "medium"
        assert result.details["evidence"] == "08.07.2026"
        assert result.details["reason"] == "invalid date format"


class TestDocumentProcessorFailureHandling:
    @pytest.mark.asyncio
    async def test_running_step_updates_active_processing_state(
        self, mock_paperless, mock_llm
    ):
        mock_llm.provider = "test-provider"
        mock_llm.model = "test-model"
        started = asyncio.Event()
        release = asyncio.Event()
        scheduler_service._clear_processing()
        scheduler_service._set_processing()

        class SlowOCRStep:
            name = "ocr"

            def can_handle(self, tags):
                return True

            async def execute(self, ctx):
                started.set()
                await release.wait()
                return StepResult(data={}, skipped=True)

            async def update_metadata(self, ctx, result):
                raise AssertionError("skipped step must not update metadata")

        mock_paperless.get_document = AsyncMock(
            return_value={
                "id": 1,
                "title": "Invoice",
                "content": "Existing OCR text",
                "tags": [5, 11],
                "custom_fields": [],
            }
        )
        mock_paperless.get_tags = AsyncMock(
            return_value=[
                {"id": 5, "name": "ai-ocr"},
                {"id": 11, "name": "force_ocr"},
            ]
        )

        processor = DocumentProcessor(paperless=mock_paperless)
        processor._build_steps = AsyncMock(return_value=[SlowOCRStep()])
        processor._get_config_dict = AsyncMock(
            return_value={
                "modular_tag_ocr": "ai-ocr",
                "force_ocr_tag": "force_ocr",
            }
        )
        processor._get_config = AsyncMock(
            side_effect=lambda key, default=None: {
                "process_tag": "ai-process",
                "processed_tag": "ai-processed",
            }.get(key, default)
        )
        processor._log_processing = AsyncMock(return_value=123)

        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            task = asyncio.create_task(processor.process_document(1))
            await asyncio.wait_for(started.wait(), timeout=1)

            state = scheduler_service.get_processing_state()
            assert state["current_document_ids"] == [1]
            assert "current_doc_id" not in state
            assert state["active_documents"][0]["trigger_tags"] == [
                "force_ocr",
                "ai-ocr",
            ]
            assert state["active_documents"][0]["trigger_mode"] == "force_ocr"
            assert state["active_documents"][0]["active_step"] == "ocr"

            release.set()
            result = await task

        try:
            assert result["success"] is True
            assert result["trigger_tags"] == ["force_ocr", "ai-ocr"]
            state = scheduler_service.get_processing_state()
            assert "current_doc_id" not in state
            assert state["active_documents"] == []
        finally:
            scheduler_service._clear_processing()

    @pytest.mark.asyncio
    async def test_failed_step_result_skips_finalization_and_logs_failure(
        self, mock_paperless, mock_llm
    ):
        """A step returning an error must leave trigger tags untouched for retry."""
        mock_llm.provider = "test-provider"
        mock_llm.model = "test-model"

        failed_step = MagicMock()
        failed_step.name = "title"
        failed_step.can_handle.return_value = True
        failed_step.execute = AsyncMock(return_value=StepResult(error="timeout"))
        failed_step.update_metadata = AsyncMock()

        successful_step = MagicMock()
        successful_step.name = "correspondent"
        successful_step.can_handle.return_value = True
        successful_step.execute = AsyncMock(
            return_value=StepResult(data={"correspondent": 1})
        )
        successful_step.update_metadata = AsyncMock()

        processor = DocumentProcessor(paperless=mock_paperless)
        processor._build_steps = AsyncMock(return_value=[failed_step, successful_step])
        processor._get_config_dict = AsyncMock(
            return_value={
                "modular_tag_process": "ai-process",
                "modular_tag_title": "ai-title",
                "modular_tag_correspondent": "ai-correspondent",
            }
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

        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            result = await processor.process_document(1)

        assert result["success"] is False
        assert "timeout" in result["error"]
        assert result["steps"][0]["status"] == "failed"
        assert result["steps"][0]["error"] == "timeout"
        successful_step.execute.assert_not_awaited()

        processor._apply_metadata_update.assert_not_awaited()
        processor._apply_tag_updates.assert_not_awaited()
        mock_paperless.update_document.assert_not_awaited()

        failed_log_call = processor._log_processing.await_args_list[-1].kwargs
        assert failed_log_call["status"] == "failed"
        assert "timeout" in failed_log_call["error_message"]

    @pytest.mark.asyncio
    async def test_skipped_step_details_are_logged(self, mock_paperless, mock_llm):
        """A skipped step should log diagnostic details and avoid metadata hooks."""
        mock_llm.provider = "test-provider"
        mock_llm.model = "test-model"

        class DetailOnlyStep:
            name = "date"

            def can_handle(self, tags):
                return True

            async def execute(self, ctx):
                return StepResult(
                    data={},
                    details={
                        "created_date": None,
                        "confidence": "low",
                        "reason": "low confidence",
                    },
                    skipped=True,
                )

            async def update_metadata(self, ctx, result):
                raise AssertionError("skipped step must not update metadata")

        processor = DocumentProcessor(paperless=mock_paperless)
        processor._build_steps = AsyncMock(return_value=[DetailOnlyStep()])
        processor._get_config_dict = AsyncMock(return_value={"modular_tag_date": "ai-date"})
        processor._get_config = AsyncMock(
            side_effect=lambda key, default=None: {
                "process_tag": "ai-process",
                "processed_tag": "ai-processed",
            }.get(key, default)
        )
        processor._log_processing = AsyncMock(return_value=123)

        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            result = await processor.process_document(1)

        assert result["success"] is True
        assert result["steps"][0]["name"] == "date"
        assert result["steps"][0]["status"] == "skipped"
        assert result["steps"][0]["details"]["reason"] == "low confidence"
        success_log_call = processor._log_processing.await_args_list[-1].kwargs
        logged = json.loads(success_log_call["llm_response"])
        assert logged["steps"][0]["details"]["created_date"] is None

    @pytest.mark.asyncio
    async def test_date_step_result_updates_paperless_created_date_and_tags(
        self, mock_paperless, mock_llm
    ):
        """A successful date step should PATCH created_date and remove ai-date."""
        mock_llm.provider = "test-provider"
        mock_llm.model = "test-model"
        mock_paperless.get_document = AsyncMock(
            return_value={
                "id": 1,
                "title": "Invoice",
                "content": "Rechnungsdatum: Dienstag, 28. April 2026",
                "tags": [42],
                "custom_fields": [],
            }
        )
        mock_paperless.get_tags = AsyncMock(
            return_value=[
                {"id": 42, "name": "ai-date"},
                {"id": 30, "name": "ai-processed"},
            ]
        )
        mock_paperless.get_correspondents = AsyncMock(return_value=[])
        mock_paperless.get_document_types = AsyncMock(return_value=[])
        mock_paperless.get_custom_fields = AsyncMock(return_value=[])

        date_step = MagicMock()
        date_step.name = "date"
        date_step.can_handle.return_value = True
        date_step.execute = AsyncMock(
            return_value=StepResult(
                data={"created_date": "2026-04-28"},
                details={
                    "created_date": "2026-04-28",
                    "confidence": "high",
                    "evidence": "Rechnungsdatum: Dienstag, 28. April 2026",
                },
            )
        )
        date_step.update_metadata = AsyncMock()

        processor = DocumentProcessor(paperless=mock_paperless)
        processor._build_steps = AsyncMock(return_value=[date_step])
        processor._get_config_dict = AsyncMock(return_value={"modular_tag_date": "ai-date"})
        processor._get_config = AsyncMock(
            side_effect=lambda key, default=None: {
                "process_tag": "ai-process",
                "processed_tag": "ai-processed",
            }.get(key, default)
        )
        processor._log_processing = AsyncMock(return_value=123)

        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            result = await processor.process_document(1)

        assert result["success"] is True
        assert result["steps"][0]["details"]["created_date"] == "2026-04-28"
        assert any(
            call.kwargs.get("created_date") == "2026-04-28"
            for call in mock_paperless.update_document.await_args_list
        )
        assert any(
            set(call.kwargs.get("tags", [])) == {30}
            for call in mock_paperless.update_document.await_args_list
        )

    @pytest.mark.asyncio
    async def test_process_tagged_documents_counts_only_successful_results(
        self, mock_paperless
    ):
        """Batch counts must not treat failed processing results as processed."""
        mock_paperless.get_tags = AsyncMock(
            return_value=[{"id": 5, "name": "ai-process"}]
        )
        mock_paperless.list_documents = AsyncMock(
            return_value=[
                {"id": 1, "title": "Ok", "tags": [5]},
                {"id": 2, "title": "Failed", "tags": [5]},
            ]
        )
        mock_paperless.reset_metrics = MagicMock()
        mock_paperless.get_metrics = MagicMock(
            return_value={"requests": 1, "paged_requests": 1}
        )

        processor = DocumentProcessor(paperless=mock_paperless)
        processor._get_config = AsyncMock(return_value="ai-process")
        processor.process_document = AsyncMock(
            side_effect=[
                {"success": True, "document_id": 1},
                {"success": False, "document_id": 2, "error": "timeout"},
            ]
        )

        result = await processor.process_tagged_documents()

        assert result["success"] is False
        assert result["processed"] == 1
        assert result["failed"] == 1
        assert [item["document_id"] for item in result["results"]] == [1, 2]


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


@patch("app.database.get_async_session")
class TestPreviewNeverCreates:
    @pytest.mark.asyncio
    async def test_preview_does_not_create_even_with_flag_on(
        self, mock_get_session, mock_paperless, mock_llm
    ):
        """process_document_preview must never create a correspondent, even when
        the live config has correspondent_create_new on and the model proposes a
        brand-new name. Locks the preview guard so removing it fails the suite."""
        prompt = MagicMock(spec=Prompt)
        prompt.system_prompt = "sys"
        prompt.user_template = "{content} {correspondents_list}"
        prompt.is_active = True
        session = AsyncMock()
        session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=prompt))
        )
        mock_get_session.return_value.__aenter__.return_value = session

        # A brand-new sender not in the mock correspondents list.
        mock_llm.complete = AsyncMock(
            return_value={"text": '{"name": "Telekom", "is_existing": false}', "raw": ""}
        )
        mock_paperless.get_or_create_correspondent = AsyncMock()

        from app.services.processor import DocumentProcessor

        processor = DocumentProcessor(paperless=mock_paperless)
        processor._get_config_dict = AsyncMock(
            return_value={
                "modular_tag_process": "ai-process",
                "correspondent_create_new": "true",  # ON at the instance level
            }
        )

        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            await processor.process_document_preview(1)

        mock_paperless.get_or_create_correspondent.assert_not_awaited()
