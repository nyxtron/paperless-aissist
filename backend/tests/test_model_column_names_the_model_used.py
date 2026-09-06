"""The model column names the model a run actually called (issue #51).

Every run was filed under the text model. A document that only carried
ai-ocr therefore showed the text model on the dashboard although only the
vision model had been called, and the log file said so.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import select

from app.database import get_session
from app.exceptions import LLMError
from app.models import ProcessingLog, Prompt
from app.services.processor import DocumentProcessor
from app.services.steps.base import StepContext, StepResult
from app.services.steps.correspondent_step import CorrespondentStep
from app.services.steps.date_step import DateStep
from app.services.steps.document_type_step import DocumentTypeStep
from app.services.steps.fields_step import FieldsStep
from app.services.steps.ocr_fix_step import OCRFixStep
from app.services.steps.ocr_step import OCRStep
from app.services.steps.tags_step import TagsStep
from app.services.steps.title_step import TitleStep

VISION = {"provider": "openai", "model": "qwen/qwen2.5-vl-7b"}
TEXT = {"provider": "ollama", "model": "qwen2.5:7b"}


def _handler(provider="ollama", model="qwen2.5:7b"):
    llm = MagicMock()
    llm.provider = provider
    llm.model = model
    return llm


def _ctx(models_used=(), llm=None):
    return StepContext(
        doc_id=1,
        paperless=MagicMock(),
        llm=llm or _handler(),
        config={},
        trigger_tags=set(),
        models_used=list(models_used),
    )


class TestWhichModelARunIsFiledUnder:
    def test_an_ocr_only_run_names_the_vision_model(self):
        assert DocumentProcessor._llm_used(_ctx([VISION])) == VISION

    def test_a_full_run_names_both_in_the_order_they_ran(self):
        assert DocumentProcessor._llm_used(_ctx([VISION, TEXT])) == {
            "provider": "openai, ollama",
            "model": "qwen/qwen2.5-vl-7b, qwen2.5:7b",
        }

    def test_a_text_only_run_is_filed_as_before(self):
        assert DocumentProcessor._llm_used(_ctx([TEXT, TEXT, TEXT])) == TEXT

    def test_a_run_that_asked_nothing_keeps_the_text_model(self):
        """A step that returned before asking (no content, prompt missing)
        used to be filed under the text model, and still is."""
        assert DocumentProcessor._llm_used(_ctx()) == TEXT

    def test_the_same_model_for_both_jobs_is_named_once(self):
        assert DocumentProcessor._llm_used(_ctx([TEXT, TEXT])) == TEXT

    def test_a_handler_without_names_yields_nothing(self):
        ctx = _ctx(llm=_handler(provider=None, model=None))

        assert DocumentProcessor._llm_used(ctx) == {"provider": None, "model": None}

    def test_a_handler_whose_names_are_not_strings_yields_nothing(self):
        """Nothing noted and a fallback handler that is a Mock: the row must
        not end up with a repr in it."""
        assert DocumentProcessor._llm_used(_ctx(llm=MagicMock())) == {
            "provider": None,
            "model": None,
        }

    def test_an_entry_missing_a_key_is_tolerated(self):
        assert DocumentProcessor._llm_used(_ctx([{"model": "vl"}, TEXT])) == {
            "provider": "ollama",
            "model": "vl, qwen2.5:7b",
        }


class TestNotingAHandler:
    def test_records_provider_and_model(self):
        ctx = _ctx()

        ctx.note_model(_handler("openai", "qwen-vl"))

        assert ctx.models_used == [{"provider": "openai", "model": "qwen-vl"}]

    def test_ignores_anything_that_is_not_a_name(self):
        """A Mock, None or an empty string must not reach the log row."""
        ctx = _ctx()

        ctx.note_model(MagicMock())
        ctx.note_model(_handler(None, ""))

        assert ctx.models_used == []

    def test_keeps_the_half_that_is_a_name(self):
        ctx = _ctx()

        ctx.note_model(_handler(None, "qwen-vl"))

        assert ctx.models_used == [{"model": "qwen-vl"}]

    def test_every_context_starts_with_its_own_empty_list(self):
        """Built without the argument, so the dataclass default is what is tested."""

        def fresh():
            return StepContext(
                doc_id=1, paperless=MagicMock(), llm=_handler(), config={}, trigger_tags=set()
            )

        first, second = fresh(), fresh()
        first.note_model(_handler(**VISION))

        assert first.models_used == [VISION]
        assert second.models_used == []


class TestTheOcrStepNotesTheVisionModel:
    def _pipeline(self, text="Read text", error=None):
        pipeline = MagicMock()
        pipeline.llm_handler.provider = VISION["provider"]
        pipeline.llm_handler.model = VISION["model"]
        if error is not None:
            pipeline.extract_text_from_pdf = AsyncMock(side_effect=error)
        else:
            pipeline.extract_text_from_pdf = AsyncMock(return_value={"text": text})
        return pipeline

    async def _run(self, mock_paperless, mock_llm, pipeline, enable_vision="true"):
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"modular_tag_ocr": "ai-ocr", "enable_vision": enable_vision},
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
            ) as create,
        ):
            db.return_value.__aenter__.return_value = session
            try:
                result = await step.execute(ctx)
            except LLMError as refused:
                result = refused
        return ctx, result, create

    @pytest.mark.asyncio
    async def test_after_a_successful_read(self, mock_paperless, mock_llm):
        ctx, result, _ = await self._run(mock_paperless, mock_llm, self._pipeline())

        assert result.data == {"text": "Read text"}
        assert ctx.models_used == [VISION]

    @pytest.mark.asyncio
    async def test_after_a_blank_page(self, mock_paperless, mock_llm):
        ctx, result, _ = await self._run(
            mock_paperless, mock_llm, self._pipeline(text="\n\n")
        )

        assert result.skipped is True
        assert ctx.models_used == [VISION]

    @pytest.mark.asyncio
    async def test_after_a_failed_call(self, mock_paperless, mock_llm):
        ctx, result, _ = await self._run(
            mock_paperless, mock_llm, self._pipeline(error=RuntimeError("boom"))
        )

        assert result.error == "boom"
        assert ctx.models_used == [VISION]

    @pytest.mark.asyncio
    async def test_after_a_refused_call(self, mock_paperless, mock_llm):
        """The step re-raises a provider refusal and cannot return a result;
        the model must already be on record."""
        ctx, result, _ = await self._run(
            mock_paperless, mock_llm, self._pipeline(error=LLMError("401"))
        )

        assert isinstance(result, LLMError)
        assert ctx.models_used == [VISION]

    @pytest.mark.asyncio
    async def test_not_when_vision_is_switched_off(self, mock_paperless, mock_llm):
        ctx, _, create = await self._run(
            mock_paperless, mock_llm, self._pipeline(), enable_vision="false"
        )

        create.assert_not_awaited()
        assert ctx.models_used == []

    @pytest.mark.asyncio
    async def test_not_when_the_pdf_never_arrived(self, mock_paperless, mock_llm):
        """Nothing was asked, so nothing is on record."""
        mock_paperless.get_document_file = AsyncMock(side_effect=RuntimeError("404"))

        ctx, result, _ = await self._run(mock_paperless, mock_llm, self._pipeline())

        assert result.error == "404"
        assert ctx.models_used == []


TEXT_STEPS = [
    (TitleStep, "ai-title"),
    (CorrespondentStep, "ai-correspondent"),
    (DocumentTypeStep, "ai-document-type"),
    (TagsStep, "ai-tags"),
    (FieldsStep, "ai-fields"),
    (DateStep, "ai-date"),
    (OCRFixStep, "ai-ocr-fix"),
]


class TestEveryTextStepNotesTheTextModel:
    """Whatever the step makes of the answer, the request was made."""

    async def _run(self, step_cls, tag, mock_ctx):
        mock_ctx.trigger_tags = {tag}
        mock_ctx.ocr_text = "Invoice from Amazon, dated 5 January 2024."
        mock_ctx.config["ocr_post_process"] = "true"
        # Lets the fields step reach its second request, the type-specific prompt.
        mock_ctx.detected_type = "Invoice"
        mock_ctx.llm.provider = TEXT["provider"]
        mock_ctx.llm.model = TEXT["model"]

        seen_at_call: list = []

        async def complete(*args, **kwargs):
            seen_at_call.append(list(mock_ctx.models_used))
            return {"text": "", "raw": ""}

        mock_ctx.llm.complete = AsyncMock(side_effect=complete)

        prompt = MagicMock(spec=Prompt)
        prompt.system_prompt = "You are helpful."
        prompt.user_template = "{content}"
        prompt.document_type_filter = None
        prompt.is_active = True
        session = AsyncMock()
        session.exec = AsyncMock(
            return_value=MagicMock(first=MagicMock(return_value=prompt))
        )

        step = await step_cls.from_config(mock_ctx.config)
        # The date step binds the session factory at import time, the others at call time.
        with (
            patch("app.database.get_async_session") as db,
            patch("app.services.steps.date_step.get_async_session") as date_db,
        ):
            for factory in (db, date_db):
                factory.return_value.__aenter__.return_value = session
            await step.execute(mock_ctx)
        return seen_at_call

    @pytest.mark.asyncio
    @pytest.mark.parametrize("step_cls,tag", TEXT_STEPS, ids=[s.name for s, _ in TEXT_STEPS])
    async def test_the_model_is_on_record_when_the_request_goes_out(
        self, step_cls, tag, mock_ctx
    ):
        seen_at_call = await self._run(step_cls, tag, mock_ctx)

        assert seen_at_call, f"{step_cls.name} never asked the model in this setup"
        # One note per request, already there when the request goes out.
        for nth, seen in enumerate(seen_at_call, start=1):
            assert seen == [TEXT] * nth

    @pytest.mark.asyncio
    async def test_ocr_fix_that_is_switched_off_notes_nothing(self, mock_ctx):
        """force_ocr triggers this step too; off, it must not claim the text
        model for a run that only used vision."""
        mock_ctx.trigger_tags = {"ai-ocr-fix"}
        mock_ctx.ocr_text = "Some text"
        mock_ctx.config["ocr_post_process"] = "false"

        step = await OCRFixStep.from_config(mock_ctx.config)
        await step.execute(mock_ctx)

        assert mock_ctx.models_used == []


class TestTheRowOnTheDashboard:
    @pytest.fixture(autouse=True)
    def _clean_log(self, client):
        with get_session() as session:
            for row in session.exec(select(ProcessingLog)):
                session.delete(row)
        yield

    def _processor(self, mock_paperless, mock_llm, ocr_execute, tag_names=("ai-ocr",)):
        mock_llm.provider = "openai"
        mock_llm.model = "qwen/qwen2.5-3B-Instruct-GGUF"
        tags = [{"id": n + 1, "name": name} for n, name in enumerate(tag_names)]
        mock_paperless.get_document = AsyncMock(
            return_value={
                "id": 836,
                "title": "ScanService_004402-01",
                "content": "Read text",
                "tags": [tag["id"] for tag in tags],
            }
        )

        ocr = MagicMock()
        ocr.name = "ocr"
        ocr.can_handle.return_value = True
        ocr.execute = AsyncMock(side_effect=ocr_execute)
        ocr.update_metadata = AsyncMock()

        processor = DocumentProcessor(paperless=mock_paperless)
        processor._build_steps = AsyncMock(return_value=[ocr])
        processor._get_config_dict = AsyncMock(return_value={"modular_tag_ocr": "ai-ocr"})
        processor._get_config = AsyncMock(side_effect=lambda k, d=None: d)
        processor._fetch_metadata = AsyncMock(
            return_value={
                "tags": tags,
                "correspondents": [],
                "document_types": [],
                "custom_fields": [],
            }
        )
        processor._apply_metadata_update = AsyncMock()
        processor._apply_tag_updates = AsyncMock()
        return processor

    def _row(self):
        with get_session() as session:
            row = session.exec(
                select(ProcessingLog).where(ProcessingLog.document_id == 836)
            ).first()
            return row.status, row.llm_provider, row.llm_model

    @pytest.mark.asyncio
    async def test_an_ai_ocr_run_is_filed_under_the_vision_model(
        self, mock_paperless, mock_llm
    ):
        """The reported case: the log file names the vision model, the
        dashboard named the text model that was never called."""

        async def read_page(ctx):
            ctx.note_model(_handler(**VISION))
            return StepResult(data={"text": "Read text"})

        processor = self._processor(mock_paperless, mock_llm, read_page)
        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            result = await processor.process_document(836)

        assert result["success"] is True
        assert self._row() == ("success", "openai", "qwen/qwen2.5-vl-7b")

    @pytest.mark.asyncio
    async def test_a_run_the_vision_provider_refused_is_filed_under_it(
        self, mock_paperless, mock_llm
    ):
        async def refused(ctx):
            ctx.note_model(_handler(**VISION))
            raise LLMError("401 invalid api key")

        processor = self._processor(mock_paperless, mock_llm, refused)
        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            result = await processor.process_document(836)

        assert result["success"] is False
        assert self._row() == ("failed", "openai", "qwen/qwen2.5-vl-7b")

    @pytest.mark.asyncio
    async def test_the_legacy_classify_fallback_counts_too(self, mock_paperless, mock_llm):
        """ai-ocr plus ai-process with no classification from the steps: the
        processor still asks the old combined classify prompt itself, and that
        request goes to the text model after the vision one."""
        with get_session() as session:
            session.add(
                Prompt(
                    name="classify-for-issue-51",
                    prompt_type="classify",
                    system_prompt="Classify.",
                    user_template="{content}",
                    is_active=True,
                )
            )

        async def read_page(ctx):
            ctx.note_model(_handler(**VISION))
            return StepResult(data={"text": "Read text"})

        try:
            processor = self._processor(
                mock_paperless, mock_llm, read_page, tag_names=("ai-ocr", "ai-process")
            )
            mock_llm.complete = AsyncMock(return_value={"text": "", "raw": ""})
            with patch(
                "app.services.processor.LLMHandlerManager.get_handler",
                AsyncMock(return_value=mock_llm),
            ):
                result = await processor.process_document(836)
        finally:
            with get_session() as session:
                for row in session.exec(
                    select(Prompt).where(Prompt.name == "classify-for-issue-51")
                ):
                    session.delete(row)

        assert result["success"] is True
        mock_llm.complete.assert_awaited_once()
        assert self._row() == (
            "success",
            "openai",
            "qwen/qwen2.5-vl-7b, qwen/qwen2.5-3B-Instruct-GGUF",
        )

    @pytest.mark.asyncio
    async def test_a_run_paperless_rejected_is_still_filed_under_the_vision_model(
        self, mock_paperless, mock_llm
    ):
        """The third log site: the steps went fine, writing back did not."""

        async def read_page(ctx):
            ctx.note_model(_handler(**VISION))
            return StepResult(data={"text": "Read text"})

        processor = self._processor(mock_paperless, mock_llm, read_page)
        processor._apply_metadata_update = AsyncMock(side_effect=RuntimeError("500"))
        with patch(
            "app.services.processor.LLMHandlerManager.get_handler",
            AsyncMock(return_value=mock_llm),
        ):
            result = await processor.process_document(836)

        assert result["success"] is False
        assert "Paperless update failed" in result["error"]
        assert self._row() == ("failed", "openai", "qwen/qwen2.5-vl-7b")
