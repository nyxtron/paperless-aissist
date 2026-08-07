"""Custom field extraction must not invent fields from the model's prose.

Three defects fed junk into Paperless custom fields:
- the bundled extract sample asks for a bare JSON array, which the step rejected
- commentary keys next to a proper custom_fields array were harvested as fields
- the {"raw": ...} fallback from llm_handler became a field called "raw"
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import Prompt
from app.services.steps.base import StepContext
from app.services.steps.fields_step import FieldsStep

parse = FieldsStep._extract_fields_from_result


def test_bare_array_is_accepted():
    """The bundled sample prompt asks for exactly this shape."""
    assert parse([{"field": "rechnungsbetrag", "value": "EUR84.99"}]) == {
        "rechnungsbetrag": "EUR84.99"
    }


def test_custom_fields_object_is_accepted():
    assert parse({"custom_fields": [{"field": "summe", "value": "12,90"}]}) == {
        "summe": "12,90"
    }


def test_commentary_next_to_an_array_is_ignored():
    """A model that adds a note must not create a field called 'note'."""
    result = parse(
        {
            "custom_fields": [{"field": "summe", "value": "12,90"}],
            "note": "sonst nichts gefunden",
        }
    )
    assert result == {"summe": "12,90"}


def test_raw_fallback_creates_no_field():
    """llm_handler returns {"raw": ...} when the reply is not valid JSON."""
    assert parse({"raw": "Ich konnte nichts finden."}) == {}


def test_flat_object_still_works():
    """Older prompts return a flat mapping — keep supporting them."""
    assert parse({"rechnungsbetrag": "EUR10.00"}) == {"rechnungsbetrag": "EUR10.00"}


def test_extract_wrapper_still_works():
    assert parse({"extract": {"Rechnungs_Nummer": "R-42"}}) == {"rechnungs nummer": "R-42"}


def test_empty_results_stay_empty():
    assert parse([]) == {}
    assert parse({"custom_fields": []}) == {}


class TestBundledSampleShapeReachesParaperless:
    """The end-to-end path: a sample-shaped reply must produce a field."""

    @pytest.mark.asyncio
    async def test_bare_array_reply_is_written(self, mock_paperless, mock_llm):
        mock_paperless.get_custom_fields = AsyncMock(
            return_value=[{"id": 7, "name": "rechnungsbetrag"}]
        )
        mock_paperless.get_document = AsyncMock(
            return_value={"id": 1, "title": "R", "content": "x", "tags": [], "custom_fields": []}
        )
        ctx = StepContext(
            doc_id=1,
            paperless=mock_paperless,
            llm=mock_llm,
            config={"modular_tag_fields": "ai-fields"},
            trigger_tags={"ai-fields"},
            ocr_text="Rechnungsbetrag EUR84.99",
        )
        # exactly what examples/prompts/custom-fields-extraction.json asks for
        mock_llm.complete = AsyncMock(
            return_value=[{"field": "rechnungsbetrag", "value": "EUR84.99"}]
        )

        prompt = MagicMock(spec=Prompt)
        prompt.system_prompt = "s"
        prompt.user_template = "{content} {custom_fields_list}"
        prompt.is_active = True
        session = AsyncMock()
        session.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=prompt)))

        with patch("app.database.get_async_session") as gs:
            gs.return_value.__aenter__.return_value = session
            step = await FieldsStep.from_config(ctx.config)
            result = await step.execute(ctx)

        assert result.data["custom_fields"] == [{"field": 7, "value": "EUR84.99"}]
