"""Type-specific field prompts are found whatever the capitalisation.

The document type step matched the reply ignoring case but stored the model's
own spelling, and the fields step then looked the prompt up by exact name: a
reply of "rechnung" set the type Rechnung and skipped the Rechnung prompt. The
filter in the prompt editor is typed by hand, so it can differ in case too.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import select

from app.database import get_session
from app.models import Prompt
from app.services.steps.base import StepContext
from app.services.steps.document_type_step import DocumentTypeStep
from app.services.steps.fields_step import FieldsStep


def _ctx(reply: str) -> StepContext:
    llm = MagicMock()
    llm.provider = "ollama"
    llm.model = "qwen2.5:7b"
    llm.complete = AsyncMock(return_value={"text": reply})
    paperless = MagicMock()
    paperless.get_document_types = AsyncMock(
        return_value=[{"id": 7, "name": "Rechnung"}, {"id": 8, "name": "Vertrag"}]
    )
    paperless.get_document = AsyncMock(
        return_value={"id": 1, "content": "Rechnung Nr. 4711", "custom_fields": []}
    )
    paperless.get_custom_fields = AsyncMock(return_value=[{"id": 1, "name": "Betrag"}])
    return StepContext(
        doc_id=1,
        paperless=paperless,
        llm=llm,
        config={"modular_tag_process": "ai-process"},
        trigger_tags={"ai-process"},
        ocr_text="Rechnung Nr. 4711",
    )


class TestTheDetectedTypeKeepsPaperlessSpelling:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("reply", ["rechnung", "RECHNUNG", "Rechnung"])
    async def test_whatever_the_model_writes(self, reply):
        ctx = _ctx(reply)
        prompt = MagicMock()
        prompt.system_prompt = "Type?"
        prompt.user_template = "{document_types_list}\n{content}"
        session = AsyncMock()
        session.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=prompt)))

        with patch("app.database.get_async_session") as db:
            db.return_value.__aenter__.return_value = session
            result = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)

        assert result.data == {"document_type": 7}
        assert ctx.detected_type == "Rechnung"


@pytest.fixture
def _prompts(client):
    """Real prompt rows, so the lookup runs as SQL against SQLite."""
    names = []

    def add(**fields):
        with get_session() as session:
            session.add(Prompt(**fields))
        names.append(fields["name"])

    yield add
    with get_session() as session:
        for row in session.exec(select(Prompt).where(Prompt.name.in_(names))):
            session.delete(row)


class TestTheFieldsStepFindsThePrompt:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "typed_filter,detected",
        [
            ("Rechnung", "Rechnung"),
            ("rechnung", "Rechnung"),
            ("RECHNUNG", "Rechnung"),
            ("Rechnung ", "Rechnung"),
            # SQLite's own lower() only knows A to Z.
            ("Überweisung", "Überweisung"),
            ("überweisung", "Überweisung"),
            ("ÄRZTLICHE BESCHEINIGUNG", "Ärztliche Bescheinigung"),
            ("STRASSENREINIGUNG", "Straßenreinigung"),
        ],
    )
    async def test_a_filter_typed_in_any_case(self, _prompts, typed_filter, detected):
        _prompts(
            name=f"type-specific-{typed_filter}",
            prompt_type="type_specific",
            document_type_filter=typed_filter,
            system_prompt="Rechnungsfelder",
            user_template="{content}",
            is_active=True,
        )
        ctx = _ctx('[{"field": "Betrag", "value": "12,00"}]')
        ctx.llm.complete = AsyncMock(return_value=[{"field": "Betrag", "value": "12,00"}])
        ctx.detected_type = detected

        result = await (await FieldsStep.from_config(ctx.config)).execute(ctx)

        systems = [call.kwargs["system_prompt"] for call in ctx.llm.complete.await_args_list]
        assert "Rechnungsfelder" in systems
        assert result.data == {"custom_fields": [{"field": 1, "value": "12,00"}]}

    @pytest.mark.asyncio
    async def test_a_switched_off_prompt_is_not_used(self, _prompts):
        _prompts(
            name="type-specific-inactive",
            prompt_type="type_specific",
            document_type_filter="Rechnung",
            system_prompt="Rechnungsfelder",
            user_template="{content}",
            is_active=False,
        )
        ctx = _ctx("[]")
        ctx.llm.complete = AsyncMock(return_value=[])
        ctx.detected_type = "Rechnung"

        await (await FieldsStep.from_config(ctx.config)).execute(ctx)

        systems = [call.kwargs["system_prompt"] for call in ctx.llm.complete.await_args_list]
        assert "Rechnungsfelder" not in systems

    @pytest.mark.asyncio
    async def test_another_type_still_gets_nothing(self, _prompts):
        _prompts(
            name="type-specific-vertrag-guard",
            prompt_type="type_specific",
            document_type_filter="Rechnung",
            system_prompt="Rechnungsfelder",
            user_template="{content}",
            is_active=True,
        )
        ctx = _ctx("[]")
        ctx.llm.complete = AsyncMock(return_value=[])
        ctx.detected_type = "Vertrag"

        await (await FieldsStep.from_config(ctx.config)).execute(ctx)

        systems = [call.kwargs["system_prompt"] for call in ctx.llm.complete.await_args_list]
        assert "Rechnungsfelder" not in systems
