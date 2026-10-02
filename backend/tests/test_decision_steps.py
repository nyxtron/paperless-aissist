"""The two decision steps at execute level, on real prompt rows and a fake
service, with values away from the defaults so a step that ignored a setting
would show."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from app.database import get_session
from app.exceptions import LLMUnavailableError
from app.models import Prompt
from app.services.decision import NONE_LABEL, Decision
from app.services.steps.base import StepContext
from app.services.steps.correspondent_step import CorrespondentStep

CORRESPONDENTS = [{"id": 11, "name": "Amazon"}, {"id": 12, "name": "Telekom"}, {"id": 13, "name": "Telekom"}]
CONFIG = {"decision_correspondent": "true", "decision_threshold_correspondent": "0.75",
          "review_tag": "needs-check", "modular_tag_process": "ai-process"}


class FakeService:
    provider, model, method = "ollama", "fake", "ollama_letters"

    def __init__(self, **decision):
        base = dict(method="ollama_letters", provider="ollama", model="fake", requests=1, rendered="[r]", top=[])
        base.update(decision)
        self.decision = Decision(**base)
        self.calls = []

    async def decide(self, text, field, options, *, question, threshold, ctx=None):
        self.calls.append(dict(text=text, field=field, options=list(options), question=question, threshold=threshold))
        if ctx is not None:
            ctx.note_model(self)
        return self.decision


@pytest.fixture
def text_prompt(client):
    """The ordinary correspondent prompt, needed by the create path."""
    with get_session() as session:
        session.add(Prompt(name="corr-text-test", prompt_type="correspondent", system_prompt="Name the sender as JSON.",
                           user_template="{content} {correspondents_list}", is_active=True))
    yield
    with get_session() as session:
        for row in session.exec(select(Prompt).where(Prompt.name == "corr-text-test")):
            session.delete(row)


def _ctx(service, config=None, paperless=None, preview=False):
    p = paperless or AsyncMock()
    p.get_correspondents = AsyncMock(return_value=CORRESPONDENTS)
    p.get_document = AsyncMock(return_value={"id": 1, "content": "Rechnung Telekom", "tags": []})
    llm = AsyncMock()
    llm.provider, llm.model = "ollama", "qwen2.5:7b"
    return StepContext(doc_id=1, paperless=p, llm=llm, config=config or CONFIG, trigger_tags={"ai-process"},
                       ocr_text="Rechnung Telekom", decision=service, preview=preview)


async def _run(ctx):
    return await (await CorrespondentStep.from_config(ctx.config)).execute(ctx)


class TestCorrespondentDecision:
    @pytest.mark.asyncio
    async def test_a_sure_answer_is_written_by_position(self):
        svc = FakeService(index=2, choice="Telekom", probability=0.8)
        ctx = _ctx(svc)
        r = await _run(ctx)
        assert r.data == {"correspondent": 13} and ctx.decided_fields == {"correspondent"}
        assert r.details["decision"]["outcome"] == "applied" and r.details["decision"]["threshold"] == 0.75
        assert svc.calls[0]["options"] == ["Amazon", "Telekom", "Telekom"] and svc.calls[0]["threshold"] == 0.75
        assert ctx.models_used == [{"provider": "ollama", "model": "fake"}]

    @pytest.mark.asyncio
    async def test_the_question_and_the_cut_text_reach_the_service(self):
        svc = FakeService(index=0, choice="Amazon", probability=0.9)
        ctx = _ctx(svc, {**CONFIG, "decision_question_correspondent": "Wer schickt das?"})
        ctx.ocr_text = "x" * 12000
        await _run(ctx)
        assert svc.calls[0]["question"] == "Wer schickt das?" and len(svc.calls[0]["text"]) == 10000

    @pytest.mark.asyncio
    async def test_below_the_threshold_is_a_review(self, text_prompt):
        ctx = _ctx(FakeService(index=1, choice="Telekom", probability=0.7))
        r = await _run(ctx)
        assert r.skipped and r.data == {} and ctx.review_fields == ["correspondent"] and not ctx.decided_fields
        assert r.details["decision"]["reason"] == "below_threshold"
        ctx.llm.complete.assert_not_awaited()
        assert "suggestion" not in r.details["decision"]

    @pytest.mark.asyncio
    async def test_none_below_the_threshold_is_a_review_without_a_text_call(self, text_prompt):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.6))
        r = await _run(ctx)
        assert r.details["decision"]["reason"] == "below_threshold" and ctx.llm.complete.await_count == 0

    @pytest.mark.asyncio
    async def test_a_tournament_review_is_passed_on(self, text_prompt):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.8, review_reason="final_none"))
        r = await _run(ctx)
        assert r.details["decision"]["reason"] == "final_none" and ctx.review_fields == ["correspondent"]
        # Only a confident "None of these" with creation off asks for a sender hint.
        ctx.llm.complete.assert_not_awaited()
        assert "suggestion" not in r.details["decision"]

    @pytest.mark.asyncio
    async def test_none_with_creation_off_is_a_review(self):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95))
        r = await _run(ctx)
        assert r.details["decision"]["reason"] == "creation_off"

    @pytest.mark.asyncio
    async def test_creation_off_still_names_the_sender_as_a_suggestion(self, text_prompt):
        p = AsyncMock()
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95), paperless=p)
        ctx.llm.complete = AsyncMock(return_value={"name": "Nadine-Fotogenial", "is_existing": False})
        r = await _run(ctx)
        assert (r.data, r.details["decision"]["outcome"], r.details["decision"]["reason"]) == ({}, "review", "creation_off")
        assert r.details["decision"]["suggestion"] == "Nadine-Fotogenial"
        assert ctx.review_fields == ["correspondent"] and "correspondent" not in ctx.decided_fields
        ctx.llm.complete.assert_awaited_once()
        p.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", ["Keine Sorgen GmbH", "Not Found GmbH", "Kein & Aber", "Nadine Schwarz."])
    async def test_a_real_name_with_a_telling_word_is_kept(self, text_prompt, name):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95))
        ctx.llm.complete = AsyncMock(return_value={"name": name, "is_existing": False})
        r = await _run(ctx)
        assert r.details["decision"]["suggestion"] == name.rstrip(".")

    @pytest.mark.asyncio
    async def test_a_new_sender_the_model_calls_known_is_still_suggested(self, text_prompt):
        # Seen live: {"name": "IONITY GmbH", "is_existing": true} for a sender not in Paperless.
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95))
        ctx.llm.complete = AsyncMock(return_value={"name": "IONITY GmbH", "is_existing": True})
        r = await _run(ctx)
        assert r.details["decision"]["suggestion"] == "IONITY GmbH"

    @pytest.mark.asyncio
    async def test_a_bare_name_from_an_older_prompt_is_suggested_too(self, text_prompt):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95))
        ctx.llm.complete = AsyncMock(return_value={"text": "Nadine-Fotogenial"})
        r = await _run(ctx)
        assert r.details["decision"]["suggestion"] == "Nadine-Fotogenial"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "reply",
        [{"name": "None", "is_existing": False}, {"name": ""}, {"text": "None"}, {"text": "Unbekannt."},
         {"text": "Der Absender dieses Dokuments ist leider nicht eindeutig zu erkennen."}],
    )
    async def test_no_usable_name_gives_no_suggestion(self, text_prompt, reply):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95))
        ctx.llm.complete = AsyncMock(return_value=reply)
        r = await _run(ctx)
        assert r.details["decision"]["reason"] == "creation_off" and "suggestion" not in r.details["decision"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "reply",
        [{"name": "amazon", "is_existing": True}, {"name": "Telekom", "is_existing": False}, {"text": "Amazon"},
         {"text": '{"name": null, "is_existing": false}'}, {"text": "Absender: Telekom GmbH"}, {"text": "?"},
         {"text": "Not found"}, {"text": "Kein Absender erkennbar"}, {"text": "Unbekannter Absender"},
         {"text": "Not found!"}, {"text": "Keiner"}, {"text": "-"}, {"text": "N.A."},
         {"name": "Unknown sender", "is_existing": False}, {"name": "?", "is_existing": False}, {"text": "Telekom."}],
    )
    async def test_a_listed_name_or_a_non_answer_is_no_suggestion(self, text_prompt, reply):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95))
        ctx.llm.complete = AsyncMock(return_value=reply)
        r = await _run(ctx)
        assert r.details["decision"]["reason"] == "creation_off" and "suggestion" not in r.details["decision"]

    @pytest.mark.asyncio
    async def test_the_preview_shows_the_suggestion_too(self, text_prompt):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95), preview=True)
        ctx.llm.complete = AsyncMock(return_value={"name": "Nadine-Fotogenial", "is_existing": False})
        r = await _run(ctx)
        assert r.details["decision"]["suggestion"] == "Nadine-Fotogenial"

    @pytest.mark.asyncio
    async def test_any_error_while_asking_costs_only_the_suggestion(self, text_prompt):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95))
        ctx.llm.complete = AsyncMock(side_effect=RuntimeError("bad reply"))
        r = await _run(ctx)
        assert (r.error, r.details["decision"]["reason"]) == (None, "creation_off")
        assert "suggestion" not in r.details["decision"]

    @pytest.mark.asyncio
    async def test_a_hanging_text_model_is_not_waited_for_in_full(self, text_prompt):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95))
        ctx.llm.timeout = 0.05

        async def hang(**kwargs):
            await asyncio.sleep(5)

        ctx.llm.complete = AsyncMock(side_effect=hang)
        started = time.monotonic()
        r = await _run(ctx)
        assert time.monotonic() - started < 2
        assert (r.error, r.details["decision"]["reason"]) == (None, "creation_off")
        assert "suggestion" not in r.details["decision"]

    @pytest.mark.asyncio
    async def test_a_failing_text_model_costs_only_the_suggestion(self, text_prompt):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95))
        ctx.llm.complete = AsyncMock(side_effect=LLMUnavailableError("ollama request failed: connect"))
        r = await _run(ctx)
        assert (r.error, r.details["decision"]["reason"]) == (None, "creation_off")
        assert "suggestion" not in r.details["decision"]

    @pytest.mark.asyncio
    async def test_without_a_text_prompt_nothing_is_asked(self):
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95))
        with patch.object(CorrespondentStep, "_load_prompt", AsyncMock(return_value=None)):
            r = await _run(ctx)
        assert "suggestion" not in r.details["decision"]
        ctx.llm.complete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_none_with_creation_on_asks_the_text_model_and_creates(self, text_prompt):
        p = AsyncMock()
        p.get_or_create_correspondent = AsyncMock(return_value=({"id": 99, "name": "Neue GmbH"}, True))
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95), {**CONFIG, "correspondent_create_new": "true"}, p)
        ctx.llm.complete = AsyncMock(return_value={"name": "Neue GmbH", "is_existing": False})
        r = await _run(ctx)
        assert r.data == {"correspondent": 99} and r.details["decision"]["outcome"] == "created"
        assert r.details["decision"]["choice"] == "Neue GmbH"
        assert r.details["created_correspondent"] == {"id": 99, "name": "Neue GmbH"}
        assert ctx.decided_fields == {"correspondent"} and ctx.models_used[-1]["model"] == "qwen2.5:7b"
        ctx.llm.complete.assert_awaited_once()
        assert "suggestion" not in r.details["decision"]

    @pytest.mark.asyncio
    async def test_a_name_that_exists_is_a_review_not_a_write(self, text_prompt):
        p = AsyncMock()
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95), {**CONFIG, "correspondent_create_new": "true"}, p)
        ctx.llm.complete = AsyncMock(return_value={"name": "amazon", "is_existing": True})
        r = await _run(ctx)
        assert r.details["decision"]["reason"] == "named_existing" and r.data == {}
        p.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reply,reason", [
        ({"text": "I think it is Neue GmbH"}, "untrusted_response"),
        ({"name": "Ganz Neu AG", "is_existing": True}, "claimed_existing_no_match"),
        ({"name": "Der Absender dieses Dokuments ist vermutlich die Firma", "is_existing": False}, "implausible_name"),
        ({"name": "None", "is_existing": False}, "no_name"),
        ({"text": "None"}, "no_name"),
    ])
    async def test_the_create_gates_become_reviews(self, text_prompt, reply, reason):
        p = AsyncMock()
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95), {**CONFIG, "correspondent_create_new": "true"}, p)
        ctx.llm.complete = AsyncMock(return_value=reply)
        r = await _run(ctx)
        assert r.details["decision"]["reason"] == reason
        p.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_create_is_a_review(self, text_prompt):
        p = AsyncMock()
        p.get_or_create_correspondent = AsyncMock(side_effect=RuntimeError("409"))
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95), {**CONFIG, "correspondent_create_new": "true"}, p)
        ctx.llm.complete = AsyncMock(return_value={"name": "Neue GmbH", "is_existing": False})
        assert (await _run(ctx)).details["decision"]["reason"] == "create_failed"

    @pytest.mark.asyncio
    async def test_a_concurrent_create_counts_as_applied(self, text_prompt):
        p = AsyncMock()
        p.get_or_create_correspondent = AsyncMock(return_value=({"id": 98, "name": "Neue GmbH"}, False))
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95), {**CONFIG, "correspondent_create_new": "true"}, p)
        ctx.llm.complete = AsyncMock(return_value={"name": "Neue GmbH", "is_existing": False})
        r = await _run(ctx)
        assert r.data == {"correspondent": 98} and r.details["decision"]["outcome"] == "applied" and "correspondent" in ctx.decided_fields
        assert r.details["decision"]["choice"] == "Neue GmbH"

    @pytest.mark.asyncio
    async def test_without_a_text_prompt_the_create_path_is_a_review(self):
        # The bundled correspondent sample is seeded active, so the absence is made explicit.
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95), {**CONFIG, "correspondent_create_new": "true"})
        with patch.object(CorrespondentStep, "_load_prompt", AsyncMock(return_value=None)):
            r = await _run(ctx)
        assert r.details["decision"]["reason"] == "no_name_prompt"

    @pytest.mark.asyncio
    async def test_the_preview_predicts_a_create_without_creating(self, text_prompt):
        p = AsyncMock()
        ctx = _ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95), {**CONFIG, "correspondent_create_new": "true"}, p, preview=True)
        ctx.llm.complete = AsyncMock(return_value={"name": "Neue GmbH", "is_existing": False})
        r = await _run(ctx)
        assert r.details["decision"]["outcome"] == "would_create" and r.details["would_create"] == "Neue GmbH"
        assert r.details["decision"]["choice"] == "Neue GmbH" and "correspondent" in ctx.decided_fields
        p.get_or_create_correspondent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_fallback_runs_the_text_path_and_says_so(self, text_prompt):
        ctx = _ctx(FakeService(fallback_reason="no_logprobs", fallback_detail="200 without logprobs"))
        ctx.llm.complete = AsyncMock(return_value={"name": "Telekom", "is_existing": True})
        r = await _run(ctx)
        assert r.data == {"correspondent": 12}
        assert r.details["decision"]["outcome"] == "fallback" and r.details["decision"]["fallback_reason"] == "no_logprobs"
        assert not ctx.decided_fields

    @pytest.mark.asyncio
    async def test_a_fallback_without_a_text_prompt_keeps_the_note(self):
        ctx = _ctx(FakeService(fallback_reason="no_logprobs", fallback_detail="200 without logprobs"))
        with patch.object(CorrespondentStep, "_load_prompt", AsyncMock(return_value=None)):
            r = await _run(ctx)
        assert r.data == {} and r.error is None
        assert r.details["decision"]["outcome"] == "fallback" and r.details["decision"]["fallback_reason"] == "no_logprobs"

    @pytest.mark.asyncio
    async def test_a_text_path_failure_after_a_fallback_keeps_the_note(self, text_prompt):
        ctx = _ctx(FakeService(fallback_reason="no_logprobs", fallback_detail="200 without logprobs"))
        # first call feeds the decision branch, second call is the text path
        ctx.paperless.get_correspondents = AsyncMock(side_effect=[CORRESPONDENTS, RuntimeError("paperless down")])
        r = await _run(ctx)
        assert r.error == "paperless down" and r.data == {}
        assert r.details["decision"]["outcome"] == "fallback" and r.details["decision"]["fallback_reason"] == "no_logprobs"

    @pytest.mark.asyncio
    async def test_an_outage_in_the_decision_is_raised(self):
        svc = FakeService(index=0, choice="Amazon", probability=0.9)

        async def down(*a, **k):
            raise LLMUnavailableError("down")

        svc.decide = down
        with pytest.raises(LLMUnavailableError):
            await _run(_ctx(svc))

    @pytest.mark.asyncio
    async def test_the_toggle_off_leaves_today_s_path_alone(self, text_prompt):
        svc = FakeService(index=0, choice="Amazon", probability=0.9)
        ctx = _ctx(svc, {**CONFIG, "decision_correspondent": "false"})
        ctx.llm.complete = AsyncMock(return_value={"name": "Telekom", "is_existing": True})
        r = await _run(ctx)
        assert r.data == {"correspondent": 12} and svc.calls == [] and "decision" not in r.details

    @pytest.mark.asyncio
    async def test_the_threshold_is_read_per_document(self):
        svc = FakeService(index=0, choice="Amazon", probability=0.8)
        step = await CorrespondentStep.from_config(CONFIG)
        first = _ctx(svc)
        second = _ctx(svc, {**CONFIG, "decision_threshold_correspondent": "0.95"})
        assert (await step.execute(first)).data == {"correspondent": 11}
        assert (await step.execute(second)).skipped

    @pytest.mark.asyncio
    async def test_the_branch_reads_the_document_s_settings_not_the_step_s(self, text_prompt):
        # A cached step, or the preview's one built with creation off, holds older settings.
        p = AsyncMock()
        p.get_or_create_correspondent = AsyncMock(return_value=({"id": 99, "name": "Neue GmbH"}, True))
        svc = FakeService(index=None, choice=NONE_LABEL, probability=0.95)
        ctx = _ctx(svc, {**CONFIG, "correspondent_create_new": "true", "decision_question_correspondent": "Wer schickt das?"}, p)
        ctx.llm.complete = AsyncMock(return_value={"name": "Neue GmbH", "is_existing": False})
        step = await CorrespondentStep.from_config({"modular_tag_process": "ai-process", "correspondent_create_new": "false"})
        r = await step.execute(ctx)
        assert svc.calls[0]["question"] == "Wer schickt das?" and r.details["decision"]["outcome"] == "created"


from app.services.steps.document_type_step import DocumentTypeStep  # noqa: E402

TYPES = [{"id": 7, "name": "Rechnung"}, {"id": 8, "name": "Vertrag"}]
TYPE_CONFIG = {"decision_document_type": "true", "decision_threshold_document_type": "0.8", "modular_tag_process": "ai-process"}


def _type_ctx(service, config=None):
    ctx = _ctx(service, config or TYPE_CONFIG)
    ctx.paperless.get_document_types = AsyncMock(return_value=TYPES)
    return ctx


class TestDocumentTypeDecision:
    @pytest.mark.asyncio
    async def test_a_sure_answer_is_written_in_paperless_spelling(self):
        ctx = _type_ctx(FakeService(index=0, choice="Rechnung", probability=0.85))
        r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert r.data == {"document_type": 7} and ctx.detected_type == "Rechnung" and ctx.decided_fields == {"document_type"}

    @pytest.mark.asyncio
    async def test_exactly_the_threshold_is_sure_enough(self):
        ctx = _type_ctx(FakeService(index=1, choice="Vertrag", probability=0.8))
        r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert r.data == {"document_type": 8} and r.details["decision"]["outcome"] == "applied"
        ctx = _type_ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.8))
        r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert r.details["decision"]["reason"] == "none_of_these"

    @pytest.mark.asyncio
    async def test_the_service_gets_the_cut_text(self):
        svc = FakeService(index=0, choice="Rechnung", probability=0.85)
        ctx = _type_ctx(svc)
        ctx.ocr_text = "x" * 12000
        await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert len(svc.calls[0]["text"]) == 10000 and svc.calls[0]["field"] == "document_type"

    @pytest.mark.asyncio
    async def test_below_the_threshold_leaves_the_type_alone(self):
        ctx = _type_ctx(FakeService(index=0, choice="Rechnung", probability=0.79))
        r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert r.skipped and ctx.detected_type is None and ctx.review_fields == ["document_type"]

    @pytest.mark.asyncio
    async def test_a_sure_none_is_a_review(self):
        ctx = _type_ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.95))
        r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert r.details["decision"]["reason"] == "none_of_these"

    @pytest.mark.asyncio
    async def test_a_fallback_uses_the_text_prompt(self, client):
        with get_session() as session:
            session.add(Prompt(name="type-text-test", prompt_type="document_type", system_prompt="s",
                               user_template="{content} {document_types_list}", is_active=True))
        try:
            ctx = _type_ctx(FakeService(fallback_reason="prompt_inactive"))
            ctx.llm.complete = AsyncMock(return_value={"text": "vertrag"})
            r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
            assert r.data == {"document_type": 8} and r.details["decision"]["outcome"] == "fallback"
        finally:
            with get_session() as session:
                for row in session.exec(select(Prompt).where(Prompt.name == "type-text-test")):
                    session.delete(row)

    @pytest.mark.asyncio
    async def test_a_fallback_without_a_text_prompt_keeps_the_note(self):
        ctx = _type_ctx(FakeService(fallback_reason="no_logprobs", fallback_detail="200 without logprobs"))
        with patch.object(DocumentTypeStep, "_load_prompt", AsyncMock(return_value=None)):
            r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert r.data == {} and r.error is None
        assert r.details["decision"]["outcome"] == "fallback" and r.details["decision"]["fallback_reason"] == "no_logprobs"

    @pytest.mark.asyncio
    async def test_an_unsure_none_is_below_the_threshold(self):
        ctx = _type_ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.6))
        r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert r.details["decision"]["reason"] == "below_threshold" and ctx.llm.complete.await_count == 0

    @pytest.mark.asyncio
    async def test_a_tournament_review_is_passed_on(self):
        ctx = _type_ctx(FakeService(index=None, choice=NONE_LABEL, probability=0.85, review_reason="final_none"))
        r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert r.details["decision"]["reason"] == "final_none" and ctx.review_fields == ["document_type"]

    @pytest.mark.asyncio
    async def test_the_branch_reads_the_document_s_settings_not_the_step_s(self):
        svc = FakeService(index=1, choice="Vertrag", probability=0.85)
        ctx = _type_ctx(svc, {**TYPE_CONFIG, "decision_question_document_type": "Was ist das?"})
        step = await DocumentTypeStep.from_config({"modular_tag_process": "ai-process"})
        r = await step.execute(ctx)
        assert r.data == {"document_type": 8} and svc.calls[0]["question"] == "Was ist das?"
        assert svc.calls[0]["options"] == ["Rechnung", "Vertrag"] and svc.calls[0]["threshold"] == 0.8

    @pytest.mark.asyncio
    async def test_the_toggle_off_leaves_today_s_path_alone(self):
        svc = FakeService(index=0, choice="Rechnung", probability=0.95)
        ctx = _type_ctx(svc, {**TYPE_CONFIG, "decision_document_type": "false"})
        ctx.llm.complete = AsyncMock(return_value={"text": "Vertrag"})
        prompt = {"system_prompt": "s", "user_template": "{content} {document_types_list}"}
        with patch.object(DocumentTypeStep, "_load_prompt", AsyncMock(return_value=prompt)):
            r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert r.data == {"document_type": 8} and svc.calls == [] and "decision" not in r.details

    @pytest.mark.asyncio
    async def test_a_text_path_failure_after_a_fallback_keeps_the_note(self):
        ctx = _type_ctx(FakeService(fallback_reason="no_logprobs", fallback_detail="200 without logprobs"))
        ctx.paperless.get_document_types = AsyncMock(side_effect=[TYPES, RuntimeError("paperless down")])
        prompt = {"system_prompt": "s", "user_template": "{content} {document_types_list}"}
        with patch.object(DocumentTypeStep, "_load_prompt", AsyncMock(return_value=prompt)):
            r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert r.error == "paperless down" and r.data == {}
        assert r.details["decision"]["outcome"] == "fallback" and r.details["decision"]["fallback_reason"] == "no_logprobs"

    @pytest.mark.asyncio
    async def test_an_outage_in_the_decision_is_raised(self):
        svc = FakeService(index=0, choice="Rechnung", probability=0.95)

        async def down(*a, **k):
            raise LLMUnavailableError("down")

        svc.decide = down
        ctx = _type_ctx(svc)
        with pytest.raises(LLMUnavailableError):
            await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)

    @pytest.mark.asyncio
    async def test_any_other_failure_in_the_decision_is_a_step_error(self):
        svc = FakeService(index=0, choice="Rechnung", probability=0.95)

        async def broken(*a, **k):
            raise RuntimeError("boom")

        svc.decide = broken
        ctx = _type_ctx(svc)
        r = await (await DocumentTypeStep.from_config(ctx.config)).execute(ctx)
        assert r.error == "boom" and r.data == {} and not ctx.decided_fields and ctx.detected_type is None
