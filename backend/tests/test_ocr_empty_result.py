"""An empty OCR result must not overwrite the document (issue #43, #45).

Pages are joined with blank lines, so a document whose pages all came back
empty produces "\n\n". That is truthy, so it passed the guard in
update_metadata and replaced whatever content Paperless already held.

Blank pages themselves are normal — the back of a duplex scan legitimately
comes back empty — so a single empty page is not an error. Only a result that
carries nothing at all is refused.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.steps.base import StepContext
from app.services.steps.ocr_step import OCRStep


def _ctx(mock_paperless, mock_llm):
    return StepContext(
        doc_id=1,
        paperless=mock_paperless,
        llm=mock_llm,
        config={"modular_tag_ocr": "ai-ocr", "enable_vision": "true"},
        trigger_tags={"ai-ocr"},
        ocr_text="",
    )


async def _run(mock_paperless, mock_llm, vision_text):
    ctx = _ctx(mock_paperless, mock_llm)
    pipeline = MagicMock()
    pipeline.extract_text_from_pdf = AsyncMock(return_value={"text": vision_text})
    session = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))

    step = await OCRStep.from_config(ctx.config)
    with (
        patch("app.database.get_async_session") as db,
        patch(
            "app.services.steps.ocr_step.VisionPipeline.create",
            AsyncMock(return_value=pipeline),
        ),
    ):
        db.return_value.__aenter__.return_value = session
        result = await step.execute(ctx)
    return ctx, result


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", ["", "\n\n", "   \n \t "])
async def test_a_result_with_no_text_is_refused(blank, mock_paperless, mock_llm):
    ctx, result = await _run(mock_paperless, mock_llm, blank)

    assert result.skipped is True
    assert result.data == {}
    assert ctx.ocr_text == ""

    # update_metadata is what writes to Paperless; it must have nothing to write.
    await OCRStep(ctx.config).update_metadata(ctx, result)
    mock_paperless.update_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_document_with_one_blank_page_still_counts(mock_paperless, mock_llm):
    """The back of a duplex scan is empty and the document is still fine."""
    ctx, result = await _run(mock_paperless, mock_llm, "Front page text\n\n")

    assert result.skipped is False
    assert result.data["text"] == "Front page text\n\n"
