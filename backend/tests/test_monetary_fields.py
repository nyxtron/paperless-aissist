"""Monetary custom fields must reach Paperless in a form it accepts.

Paperless takes a plain number with at most two decimals or a three-letter
currency code followed by one ("EUR104.99"). Models answer the way invoices
are written ("104,99 €"), and one such value used to fail the whole update.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import Prompt
from app.services.steps.base import StepContext
from app.services.steps.fields_step import FieldsStep
from app.services.steps.monetary import format_monetary


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("104,99 €", "EUR104.99"),
        ("€ 104,99", "EUR104.99"),
        ("1.234,56 EUR", "EUR1234.56"),
        ("€ 1,234.56", "EUR1234.56"),
        ("1 234,56 €", "EUR1234.56"),
        ("1 234,56 €", "EUR1234.56"),
        ("CHF 1'234.50", "CHF1234.50"),
        ("1.234.567,8 EUR", "EUR1234567.80"),
        ("$12.5", "USD12.50"),
        ("US$ 12.50", "USD12.50"),
        ("£7", "GBP7.00"),
        ("12,90 Euro", "EUR12.90"),
        ("12,90 eur", "EUR12.90"),
        ("EUR84.99", "EUR84.99"),
        ("EUR 84,99", "EUR84.99"),
        ("SEK 199,00", "SEK199.00"),
        ("104,- €", "EUR104.00"),
        ("104,– €", "EUR104.00"),
        ("104,--", "104.00"),
        ("50,-- €", "EUR50.00"),
        ("€ 50,--", "EUR50.00"),
        ("50,—— €", "EUR50.00"),
        ("-50,-- €", "EUR-50.00"),
        ("1.234,- €", "EUR1234.00"),
        ("1.500,-- EUR", "EUR1500.00"),
        ("1,234.- USD", "USD1234.00"),
        ("1 234,56 €", "EUR1234.56"),
        ("+5,00 €", "EUR5.00"),
        ("SFr 100", "CHF100.00"),
        ("Fr. 100", "CHF100.00"),
        ("DM 50,--", "DEM50.00"),
        ("-5,00 €", "EUR-5.00"),
        ("−5,00 €", "EUR-5.00"),
        ("5,00- €", "EUR-5.00"),
        ("EUR-5.00", "EUR-5.00"),
        ("104.99", "104.99"),
        ("104", "104.00"),
        ("0,99", "0.99"),
        (" 42,1 ", "42.10"),
        (104.99, "104.99"),
        (104, "104.00"),
    ],
)
def test_amounts_are_formatted_for_paperless(raw, expected):
    assert format_monetary(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "1.679",  # thousands or three decimals: cannot tell
        "1,679 €",
        "12.3456",
        "1.234.56",
        "1.234,567",
        "104,99 € (netto 88,23 €)",
        "2 x 50,00 €",
        "ca. 100 €",
        "siehe Anlage",
        "",
        "   ",
        "€",
        "--5,00",
        "(104.99)",
        "12345678901,00",  # more than Paperless stores
        "1.234.-",
        "1,234,-",
        "+-5,00",
        # three letters that are not a currency
        "1,5 Mio",
        "2,5 Tsd",
        "1,2 Mrd",
        "100 net",
        "max 100",
        "10 kWh",
        "12 Stk",
        "12 Std",
        "USt 19,00",
        "NAN 12",
        "all 100",
        "12 Sek",
        True,
        None,
        [104.99],
    ],
)
def test_what_cannot_be_read_as_one_amount_is_refused(raw):
    assert format_monetary(raw) is None
    assert format_monetary(raw, default_currency="EUR") is None


def test_a_bare_dollar_or_yen_sign_follows_the_field_currency():
    assert format_monetary("$ 12.50", default_currency="CAD") == "CAD12.50"
    assert format_monetary("¥100", default_currency="CNY") == "CNY100.00"
    assert format_monetary("$12", default_currency="EUR") == "USD12.00"
    assert format_monetary("US$ 5", default_currency="CAD") == "USD5.00"
    assert format_monetary("CAD 12.50", default_currency="AUD") == "CAD12.50"
    assert format_monetary("$ 1500,50", default_currency="ARS") == "ARS1500.50"
    assert format_monetary("£ 100", default_currency="EGP") == "EGP100.00"
    assert format_monetary("£ 100", default_currency="EUR") == "GBP100.00"


def test_the_field_default_currency_fills_a_bare_number():
    assert format_monetary("104,99", default_currency="EUR") == "EUR104.99"
    assert format_monetary("104,99", default_currency="eur") == "EUR104.99"
    assert format_monetary("104,99 $", default_currency="EUR") == "USD104.99"
    assert format_monetary("104,99", default_currency="") == "104.99"
    assert format_monetary("104,99", default_currency="EURO") == "104.99"
    assert format_monetary("104,99", default_currency="XYZ") == "104.99"


def _ctx(mock_paperless, mock_llm, reply, custom_fields, doc_fields=()):
    mock_paperless.get_custom_fields = AsyncMock(return_value=custom_fields)
    mock_paperless.get_document = AsyncMock(
        return_value={"id": 1, "title": "R", "content": "x", "tags": [], "custom_fields": list(doc_fields)}
    )
    mock_llm.complete = AsyncMock(return_value=reply)
    return StepContext(
        doc_id=1,
        paperless=mock_paperless,
        llm=mock_llm,
        config={"modular_tag_fields": "ai-fields"},
        trigger_tags={"ai-fields"},
        ocr_text="Rechnungsbetrag 104,99 €",
    )


async def _run(ctx):
    prompt = MagicMock(spec=Prompt)
    prompt.system_prompt = "s"
    prompt.user_template = "{content} {custom_fields_list}"
    prompt.is_active = True
    session = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=prompt)))
    with patch("app.database.get_async_session") as gs:
        gs.return_value.__aenter__.return_value = session
        step = await FieldsStep.from_config(ctx.config)
        return await step.execute(ctx)


AMOUNT = {"id": 7, "name": "rechnungsbetrag", "data_type": "monetary",
          "extra_data": {"select_options": [], "default_currency": "EUR"}}
NUMBER = {"id": 8, "name": "rechnungsnummer", "data_type": "string", "extra_data": {}}


class TestTheStepWritesWhatPaperlessAccepts:
    @pytest.mark.asyncio
    async def test_an_invoice_style_amount_is_written_in_paperless_form(self, mock_paperless, mock_llm):
        ctx = _ctx(mock_paperless, mock_llm, [{"field": "rechnungsbetrag", "value": "104,99 €"}], [AMOUNT])
        result = await _run(ctx)
        assert result.data["custom_fields"] == [{"field": 7, "value": "EUR104.99"}]

    @pytest.mark.asyncio
    async def test_a_bare_number_takes_the_field_default_currency(self, mock_paperless, mock_llm):
        ctx = _ctx(mock_paperless, mock_llm, [{"field": "rechnungsbetrag", "value": "1.234,50"}], [AMOUNT])
        result = await _run(ctx)
        assert result.data["custom_fields"] == [{"field": 7, "value": "EUR1234.50"}]

    @pytest.mark.asyncio
    async def test_an_unreadable_amount_is_left_out_and_the_rest_written(
        self, mock_paperless, mock_llm, caplog
    ):
        reply = [{"field": "rechnungsbetrag", "value": "siehe Anlage"},
                 {"field": "rechnungsnummer", "value": "R-2026-16689"}]
        ctx = _ctx(mock_paperless, mock_llm, reply, [AMOUNT, NUMBER])
        with caplog.at_level(logging.WARNING, logger="app.services.steps.fields_step"):
            result = await _run(ctx)
        assert result.data["custom_fields"] == [{"field": 8, "value": "R-2026-16689"}]
        assert "rechnungsbetrag" in caplog.text and "siehe Anlage" in caplog.text

    @pytest.mark.asyncio
    async def test_an_unreadable_amount_keeps_the_stored_one(self, mock_paperless, mock_llm):
        ctx = _ctx(mock_paperless, mock_llm, [{"field": "rechnungsbetrag", "value": "1,679 €"}], [AMOUNT],
                   doc_fields=[{"field": 7, "value": "EUR50.00"}])
        result = await _run(ctx)
        assert result.data["custom_fields"] == [{"field": 7, "value": "EUR50.00"}]

    @pytest.mark.asyncio
    async def test_other_field_types_are_written_as_before(self, mock_paperless, mock_llm):
        ctx = _ctx(mock_paperless, mock_llm, [{"field": "rechnungsnummer", "value": "104,99 €"}], [NUMBER])
        result = await _run(ctx)
        assert result.data["custom_fields"] == [{"field": 8, "value": "104,99 €"}]
