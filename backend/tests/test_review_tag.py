"""The review tag is set and cleared in the one tag update that commits a
document, and a run never writes while the tag is missing in Paperless."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlmodel import select

from app.database import get_session
from app.models import ProcessingLog
from app.services.decision import DecisionServiceManager
from app.services.processor import DocumentProcessor
from app.services.steps.base import StepResult

TAGS = [{"id": 1, "name": "ai-process"}, {"id": 2, "name": "ai-processed"}, {"id": 3, "name": "ai-review"}, {"id": 4, "name": "Steuer"}]
DOC_ID = 4242


def _paperless(doc_tags, tags=TAGS):
    p = AsyncMock()
    p.get_document = AsyncMock(return_value={"id": DOC_ID, "title": "Doc", "content": "Rechnung Telekom", "tags": list(doc_tags)})
    p.get_tags = AsyncMock(return_value=tags)
    p.get_correspondents = AsyncMock(return_value=[{"id": 11, "name": "Telekom"}])
    p.get_document_types = AsyncMock(return_value=[{"id": 7, "name": "Rechnung"}])
    p.get_custom_fields = AsyncMock(return_value=[])
    p.reset_metrics = MagicMock()
    p.get_metrics = MagicMock(return_value={"requests": 0, "paged_requests": 0})

    async def _update(doc_id, title=None, correspondent=None, document_type=None, tags=None,
                      custom_fields=None, content=None, created_date=None):
        return {}  # the real client's keyword set: an unknown field raises TypeError

    p.update_document = AsyncMock(side_effect=_update)
    return p


def _step(name, outcome, field_id=None, reason=None):
    """A fake decision step: 'applied' writes field_id, 'review' asks for the tag, 'text' is a fallback."""
    step = MagicMock()
    step.name = name
    step.can_handle = lambda tags: "ai-process" in tags or f"ai-{name.replace('_', '-')}" in tags

    async def execute(ctx):
        if outcome == "applied":
            ctx.decided_fields.add(name)
            return StepResult(data={name: field_id}, details={"decision": {"outcome": "applied"}})
        if outcome == "review":
            ctx.review_fields.append(name)
            return StepResult(data={}, skipped=True, details={"decision": {"outcome": "review", "reason": reason or "below_threshold"}})
        return StepResult(data={name: field_id}, details={"decision": {"outcome": "fallback", "fallback_reason": "no_logprobs"}})

    step.execute = AsyncMock(side_effect=execute)
    step.update_metadata = AsyncMock()
    return step


def _preview_steps(correspondent, document_type):
    """The preview builds its own steps; patch the classes it imports."""
    from contextlib import ExitStack

    from app.services.steps import CorrespondentStep, DocumentTypeStep, FieldsStep, TagsStep, TitleStep

    stack = ExitStack()
    for cls, fake in ((CorrespondentStep, correspondent), (DocumentTypeStep, document_type),
                      (TitleStep, _step("title", "text", "T")), (TagsStep, _step("tags", "text", [])),
                      (FieldsStep, _step("fields", "text", []))):
        stack.enter_context(patch.object(cls, "from_config", AsyncMock(return_value=fake)))
    return stack


def _processor(paperless, steps, config):
    proc = DocumentProcessor(paperless=paperless)
    proc._build_steps = AsyncMock(return_value=steps)
    proc._get_config_dict = AsyncMock(return_value=config)
    proc._get_config = AsyncMock(side_effect=lambda k, d=None: config.get(k, d))
    return proc


@pytest.fixture(autouse=True)
def fake_service(client):
    service = MagicMock(is_closed=False)
    service.provider, service.model = "ollama", "nimble"
    DecisionServiceManager._service = service
    yield
    DecisionServiceManager._service = None
    with get_session() as session:
        for row in session.exec(select(ProcessingLog).where(ProcessingLog.document_id == DOC_ID)):
            session.delete(row)


BOTH_ON = {"process_tag": "ai-process", "processed_tag": "ai-processed", "decision_correspondent": "true",
           "decision_document_type": "true", "review_tag": "ai-review", "modular_tag_process": "ai-process"}
NO_REVIEW_TAG = [t for t in TAGS if t["name"] != "ai-review"]


def _tag_update(paperless):
    calls = [c for c in paperless.update_document.await_args_list if "tags" in c.kwargs]
    assert len(calls) == 1, calls
    return set(calls[0].kwargs["tags"])


def _log_row():
    with get_session() as session:
        row = session.exec(select(ProcessingLog).where(ProcessingLog.document_id == DOC_ID)).first()
        session.expunge(row)  # keeps its loaded values past the commit
        return row


@pytest.mark.asyncio
async def test_the_review_tag_rides_in_the_single_tag_update():
    p = _paperless([1])
    proc = _processor(p, [_step("correspondent", "review"), _step("document_type", "applied", 7)], BOTH_ON)
    result = await proc.process_document(DOC_ID)
    assert result["success"] and _tag_update(p) == {2, 3}
    assert result["proposed_changes"]["review"] == {"tag": {"id": 3, "name": "ai-review"}, "add_fields": ["correspondent"], "remove": False, "missing": False}


@pytest.mark.asyncio
async def test_a_fully_decided_rerun_removes_the_review_tag():
    p = _paperless([1, 3])
    proc = _processor(p, [_step("correspondent", "applied", 11), _step("document_type", "applied", 7)], BOTH_ON)
    result = await proc.process_document(DOC_ID)
    assert _tag_update(p) == {2} and result["proposed_changes"]["review"]["remove"] is True


@pytest.mark.asyncio
async def test_a_partial_run_leaves_the_review_tag():
    p = _paperless([5, 3], TAGS + [{"id": 5, "name": "ai-document-type"}])
    proc = _processor(p, [_step("correspondent", "applied", 11), _step("document_type", "applied", 7)], {**BOTH_ON, "modular_tag_document_type": "ai-document-type"})
    await proc.process_document(DOC_ID)
    assert 3 in _tag_update(p)


@pytest.mark.asyncio
async def test_a_text_fallback_leaves_the_review_tag():
    p = _paperless([1, 3])
    proc = _processor(p, [_step("correspondent", "text", 11), _step("document_type", "applied", 7)], BOTH_ON)
    await proc.process_document(DOC_ID)
    assert 3 in _tag_update(p)


@pytest.mark.asyncio
async def test_with_no_toggle_on_the_review_tag_is_never_touched():
    p = _paperless([1, 3])
    proc = _processor(p, [_step("correspondent", "applied", 11)], {**BOTH_ON, "decision_correspondent": "false", "decision_document_type": "false"})
    result = await proc.process_document(DOC_ID)
    assert 3 in _tag_update(p) and "review" not in result["proposed_changes"]


@pytest.mark.asyncio
async def test_a_dropped_reference_does_not_count_as_decided():
    p = _paperless([1, 3])
    proc = _processor(p, [_step("correspondent", "applied", 11), _step("document_type", "applied", 7)], BOTH_ON)
    proc._apply_metadata_update = AsyncMock(return_value={"correspondent"})
    await proc.process_document(DOC_ID)
    assert 3 in _tag_update(p)


@pytest.mark.asyncio
async def test_a_correspondent_paperless_no_longer_has_keeps_the_review_tag():
    """The real write path: Paperless rejects the decided correspondent as deleted."""
    p = _paperless([1, 3])
    request = httpx.Request("PATCH", f"http://p/api/documents/{DOC_ID}/")
    stale = httpx.HTTPStatusError(
        "400", request=request,
        response=httpx.Response(400, request=request, text='{"correspondent":["Invalid pk \\"11\\" - object does not exist."]}'),
    )
    p.update_document = AsyncMock(side_effect=[stale, {}, {}])
    p.get_correspondents = AsyncMock(side_effect=[[{"id": 11, "name": "Telekom"}], []])
    proc = _processor(p, [_step("correspondent", "applied", 11), _step("document_type", "applied", 7)], BOTH_ON)
    result = await proc.process_document(DOC_ID)
    assert result["success"] is True
    assert p.update_document.await_args_list[1].kwargs == {"title": None, "correspondent": None, "document_type": 7}
    assert 3 in _tag_update(p) and result["proposed_changes"]["review"]["remove"] is False


@pytest.mark.asyncio
async def test_a_missing_review_tag_stops_before_any_step():
    p = _paperless([1], NO_REVIEW_TAG)
    steps = [_step("correspondent", "review")]
    proc = _processor(p, steps, BOTH_ON)
    result = await proc.process_document(DOC_ID)
    assert result["success"] is False and result["stop_run"] == "review_tag_missing"
    assert result["provider_failure"] is False and result.get("retryable") is not True
    assert "ai-review" in result["error"]
    steps[0].execute.assert_not_awaited()
    p.update_document.assert_not_awaited()
    p.get_tags.assert_any_await(force_refresh=True)
    row = _log_row()
    assert row.status == "failed" and "ai-review" in row.error_message


@pytest.mark.asyncio
async def test_the_pre_check_only_runs_for_decision_documents():
    p = _paperless([6], NO_REVIEW_TAG + [{"id": 6, "name": "ai-title"}])
    title = MagicMock(name="title"); title.name = "title"; title.can_handle = lambda tags: "ai-title" in tags
    title.execute = AsyncMock(return_value=StepResult(data={"title": "T"})); title.update_metadata = AsyncMock()
    proc = _processor(p, [title, _step("correspondent", "review")], {**BOTH_ON, "modular_tag_title": "ai-title"})
    result = await proc.process_document(DOC_ID)
    assert result["success"] is True and "stop_run" not in result


@pytest.mark.asyncio
async def test_the_pre_check_runs_even_when_the_field_would_fall_back():
    p = _paperless([1], NO_REVIEW_TAG)
    proc = _processor(p, [_step("correspondent", "text", 11)], BOTH_ON)
    assert (await proc.process_document(DOC_ID))["stop_run"] == "review_tag_missing"


@pytest.mark.asyncio
async def test_an_unreachable_tag_list_fails_the_document_without_stopping_the_run():
    p = _paperless([1])
    p.get_tags = AsyncMock(side_effect=[TAGS, httpx.ConnectError("gone", request=httpx.Request("GET", "http://p/api/tags/"))])
    proc = _processor(p, [_step("correspondent", "review")], BOTH_ON)
    result = await proc.process_document(DOC_ID)
    assert result["success"] is False and "stop_run" not in result
    assert result["provider_failure"] is False and result["retryable"] is False
    p.update_document.assert_not_awaited()
    row = _log_row()
    assert row.status == "failed" and row.error_message.startswith("Paperless tag list unavailable")


@pytest.mark.asyncio
async def test_the_fresh_tag_list_reaches_the_classify_fallback(classify_prompt):
    """A tag created after the cache filled is offered and resolved for this document."""
    p = _paperless([1])
    fresh = TAGS + [{"id": 9, "name": "Neu"}]
    p.get_tags = AsyncMock(side_effect=[TAGS, fresh, fresh])
    quiet = _step("correspondent", "text")
    quiet.execute = AsyncMock(return_value=StepResult(data={}))
    llm = _text_llm()
    llm.complete = AsyncMock(return_value={"text": "Tags: Neu"})
    proc = _processor(p, [quiet], BOTH_ON)
    with patch("app.services.processor.LLMHandlerManager.get_handler", AsyncMock(return_value=llm)):
        await proc.process_document(DOC_ID)
    assert '"Neu"' in llm.complete.await_args.kwargs["user_prompt"]
    assert 9 in _tag_update(p)


@pytest.mark.asyncio
async def test_the_backstop_catches_a_tag_deleted_after_the_pre_check():
    p = _paperless([1])
    p.get_tags = AsyncMock(side_effect=[TAGS, TAGS, NO_REVIEW_TAG])
    proc = _processor(p, [_step("correspondent", "review")], BOTH_ON)
    result = await proc.process_document(DOC_ID)
    assert result["success"] is False and "ai-review" in result["error"]
    assert result["stop_run"] == "review_tag_missing"
    assert result["error"] == "Review tag 'ai-review' does not exist in Paperless"
    p.update_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_backstop_fails_a_fully_decided_document_too():
    p = _paperless([1, 3])
    p.get_tags = AsyncMock(side_effect=[TAGS, TAGS, NO_REVIEW_TAG])
    proc = _processor(p, [_step("correspondent", "applied", 11), _step("document_type", "applied", 7)], BOTH_ON)
    result = await proc.process_document(DOC_ID)
    assert result["stop_run"] == "review_tag_missing"
    p.update_document.assert_not_awaited()
    row = _log_row()
    assert row.status == "failed" and row.error_message == "Review tag 'ai-review' does not exist in Paperless"


@pytest.mark.asyncio
async def test_review_in_step_data_fails_the_commit_test():
    """Nothing a step puts in data may be named review: it would reach update_document(**)."""
    p = _paperless([1])
    bad = _step("correspondent", "applied", 11)

    async def execute(ctx):
        return StepResult(data={"review": {"x": 1}})

    bad.execute = AsyncMock(side_effect=execute)
    proc = _processor(p, [bad], BOTH_ON)
    result = await proc.process_document(DOC_ID)
    assert result["success"] is False


@pytest.fixture
def classify_prompt(client):
    from app.models import Prompt

    with get_session() as session:
        session.add(Prompt(name="classify-review-test", prompt_type="classify", system_prompt="Classify.",
                           user_template="{content} {correspondents_list} {tags_list}", is_active=True))
    yield
    with get_session() as session:
        for row in session.exec(select(Prompt).where(Prompt.name == "classify-review-test")):
            session.delete(row)


def _text_llm():
    llm = AsyncMock()
    llm.provider, llm.model = "ollama", "qwen2.5:7b"
    llm.complete = AsyncMock(return_value={"text": "Correspondent: Telekom"})
    return llm


@pytest.mark.asyncio
async def test_the_classify_fallback_is_skipped_when_a_field_waits(classify_prompt):
    p = _paperless([1])
    llm = _text_llm()
    proc = _processor(p, [_step("correspondent", "review")], BOTH_ON)
    with patch("app.services.processor.LLMHandlerManager.get_handler", AsyncMock(return_value=llm)):
        await proc.process_document(DOC_ID)
    llm.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_classify_fallback_still_runs_when_nothing_waits(classify_prompt):
    p = _paperless([1])
    llm = _text_llm()
    step = _step("correspondent", "text")
    step.execute = AsyncMock(return_value=StepResult(data={}))
    proc = _processor(p, [step], {**BOTH_ON, "decision_correspondent": "false", "decision_document_type": "false"})
    with patch("app.services.processor.LLMHandlerManager.get_handler", AsyncMock(return_value=llm)):
        await proc.process_document(DOC_ID)
    llm.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_log_row_names_the_decision_model_when_only_it_was_asked():
    p = _paperless([1])
    step = _step("correspondent", "applied", 11)

    async def execute(ctx):
        ctx.note_model(ctx.decision)
        ctx.decided_fields.add("correspondent")
        return StepResult(data={"correspondent": 11}, details={"decision": {"outcome": "applied"}})

    step.execute = AsyncMock(side_effect=execute)
    proc = _processor(p, [step], {**BOTH_ON, "decision_document_type": "false"})
    await proc.process_document(DOC_ID)
    assert _log_row().llm_model == "nimble"


@pytest.mark.asyncio
async def test_the_preview_predicts_add_and_remove_and_writes_nothing():
    p = _paperless([1, 3])
    proc = _processor(p, [], BOTH_ON)
    with _preview_steps(_step("correspondent", "applied", 11), _step("document_type", "applied", 7)):
        result = await proc.process_document_preview(DOC_ID)
    assert result["proposed_changes"]["review"] == {"tag": {"id": 3, "name": "ai-review"}, "add_fields": [], "remove": True, "missing": False}
    p.update_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_preview_steps_get_the_service_and_never_write():
    p = _paperless([1, 3])
    correspondent = _step("correspondent", "applied", 11)
    proc = _processor(p, [], BOTH_ON)
    with _preview_steps(correspondent, _step("document_type", "applied", 7)):
        await proc.process_document_preview(DOC_ID)
    ctx = correspondent.execute.await_args.args[0]
    assert ctx.preview is True and ctx.decision is DecisionServiceManager._service


@pytest.mark.asyncio
async def test_the_preview_flags_a_missing_tag_and_still_shows_decisions():
    p = _paperless([1], NO_REVIEW_TAG)
    proc = _processor(p, [], BOTH_ON)
    with _preview_steps(_step("correspondent", "review"), _step("document_type", "applied", 7)):
        result = await proc.process_document_preview(DOC_ID)
    review = result["proposed_changes"]["review"]
    assert review["missing"] is True and review["tag"] == {"id": None, "name": "ai-review"} and review["add_fields"] == ["correspondent"]
    assert any(s["name"] == "correspondent" and s["details"]["decision"]["outcome"] == "review" for s in result["steps"])


@pytest.mark.asyncio
async def test_stored_details_hold_no_full_request():
    p = _paperless([1])
    step = _step("correspondent", "applied", 11)

    async def execute(ctx):
        ctx.decided_fields.add("correspondent")
        return StepResult(data={"correspondent": 11}, details={"decision": {"outcome": "applied", "request": {"rendered": "r", "full": "the text"}}})

    step.execute = AsyncMock(side_effect=execute)
    proc = _processor(p, [step], BOTH_ON)
    await proc.process_document(DOC_ID)
    row = _log_row()
    assert "the text" not in row.llm_response and "full" not in json.loads(row.llm_response)["steps"][0]["details"]["decision"]["request"]
