"""Steps must let a provider failure through (issue #43, #46).

Every step but date and fields used to catch the LLM error in its own broad
handler and hand back a StepResult, so the run could not tell a dead provider
from one unreadable document — and the batch had no reason to stop.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import LLMError, LLMUnavailableError
from app.services.steps.base import StepContext
from app.services.steps.correspondent_step import CorrespondentStep
from app.services.steps.document_type_step import DocumentTypeStep
from app.services.steps.fields_step import FieldsStep
from app.services.steps.tags_step import TagsStep
from app.services.steps.title_step import TitleStep

STEPS = [
    ("title", TitleStep, "modular_tag_title", "ai-title"),
    ("correspondent", CorrespondentStep, "modular_tag_correspondent", "ai-correspondent"),
    ("document_type", DocumentTypeStep, "modular_tag_document_type", "ai-document-type"),
    ("tags", TagsStep, "modular_tag_tags", "ai-tags"),
    ("fields", FieldsStep, "modular_tag_fields", "ai-fields"),
]


def _prompt_session():
    prompt = MagicMock()
    prompt.system_prompt = "s"
    prompt.user_template = "{content}"
    prompt.is_active = True
    prompt.document_type_filter = None
    session = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=prompt)))
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("name,step_cls,config_key,tag", STEPS)
@pytest.mark.parametrize("error", [LLMError("refused"), LLMUnavailableError("down")])
async def test_the_step_does_not_swallow_it(
    name, step_cls, config_key, tag, error, mock_paperless, mock_llm
):
    mock_llm.complete = AsyncMock(side_effect=error)
    config = {config_key: tag}
    ctx = StepContext(
        doc_id=1,
        paperless=mock_paperless,
        llm=mock_llm,
        config=config,
        trigger_tags={tag},
        ocr_text="Invoice text for the model to read.",
    )
    step = await step_cls.from_config(config)

    with (
        patch("app.database.get_async_session") as db,
        patch(f"app.services.steps.{name}_step.get_async_session", create=True) as local,
    ):
        db.return_value.__aenter__.return_value = _prompt_session()
        local.return_value.__aenter__.return_value = _prompt_session()
        with pytest.raises(LLMError):
            await step.execute(ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [LLMError("refused"), LLMUnavailableError("down")])
async def test_the_ocr_fix_step_does_not_swallow_it(error, mock_paperless, mock_llm):
    from app.services.steps.ocr_fix_step import OCRFixStep

    mock_llm.complete = AsyncMock(side_effect=error)
    config = {
        "modular_tag_ocr_fix": "ai-ocr-fix",
        "ocr_fix_max_chars": "10000",
        "ocr_post_process": "true",
    }
    ctx = StepContext(
        doc_id=1,
        paperless=mock_paperless,
        llm=mock_llm,
        config=config,
        trigger_tags={"ai-ocr-fix"},
        ocr_text="Scanned text with 0CR errors that wants fixing.",
    )
    step = await OCRFixStep.from_config(config)

    with patch("app.database.get_async_session") as db:
        db.return_value.__aenter__.return_value = _prompt_session()
        with pytest.raises(LLMError):
            await step.execute(ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [LLMError("refused"), LLMUnavailableError("down")])
async def test_the_ocr_step_does_not_swallow_it(error, mock_paperless, mock_llm):
    """OCR goes through the vision pipeline rather than llm.complete."""
    from app.services.steps.ocr_step import OCRStep

    config = {"modular_tag_ocr": "ai-ocr", "enable_vision": "true"}
    ctx = StepContext(
        doc_id=1,
        paperless=mock_paperless,
        llm=mock_llm,
        config=config,
        trigger_tags={"ai-ocr"},
        ocr_text="",
    )
    step = await OCRStep.from_config(config)

    pipeline = MagicMock()
    pipeline.extract_text_from_pdf = AsyncMock(side_effect=error)

    with (
        patch("app.database.get_async_session") as db,
        patch(
            "app.services.steps.ocr_step.VisionPipeline.create",
            AsyncMock(return_value=pipeline),
        ),
    ):
        db.return_value.__aenter__.return_value = _prompt_session()
        with pytest.raises(LLMError):
            await step.execute(ctx)
