"""One missing review tag stops the whole run at once, in both loops, and the
state file says why, in a way the page can tell apart from a hand stop."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import scheduler
from app.services.processor import DocumentProcessor

STOP = {"success": False, "provider_failure": False, "retryable": False, "stop_run": "review_tag_missing",
        "error": "Review tag 'ai-review' does not exist in Paperless", "document_id": 1}
OK = {"success": True, "document_id": 2}


@pytest.fixture(autouse=True)
def clean_state():
    # last_stop outlives a run, so wipe it too: a stop left by the test before
    # must not pass for one this test was meant to record.
    scheduler._clear_processing()
    scheduler._save_state(scheduler._default_state())
    yield
    scheduler._clear_processing()
    scheduler._save_state(scheduler._default_state())


@pytest.mark.asyncio
async def test_the_legacy_loop_stops_at_once_whatever_the_failure_limit():
    p = AsyncMock()
    p.reset_metrics = MagicMock()
    p.get_metrics = MagicMock(return_value={"requests": 0, "paged_requests": 0})
    p.get_tags = AsyncMock(return_value=[{"id": 1, "name": "ai-process"}])
    p.list_documents = AsyncMock(return_value=[{"id": 1}, {"id": 2}, {"id": 3}])
    proc = DocumentProcessor(paperless=p)
    proc._get_config = AsyncMock(return_value="ai-process")
    proc.process_document = AsyncMock(side_effect=[STOP, OK, OK])
    with patch("app.services.scheduler.get_max_consecutive_failures", AsyncMock(return_value=0)):
        result = await proc.process_tagged_documents()
    assert proc.process_document.await_count == 1
    assert result["stop"] == {"reason": STOP["error"], "kind": "review_tag"}
    assert scheduler._load_state()["last_stop"]["kind"] == "review_tag"
    assert scheduler._load_state()["last_stop"]["reason"] == STOP["error"]


@pytest.mark.asyncio
async def test_the_modular_loop_lets_queued_documents_bow_out():
    calls = []

    async def process_one(doc_id):
        calls.append(doc_id)
        return STOP if doc_id == 1 else OK

    paperless = AsyncMock()
    paperless.reset_metrics = MagicMock()
    paperless.get_metrics = MagicMock(return_value={"requests": 0, "paged_requests": 0})
    paperless.get_tags = AsyncMock(return_value=[{"id": 9, "name": "ai-title"}])
    paperless.list_documents = AsyncMock(return_value=[{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}])
    with patch("app.services.paperless_manager.PaperlessClientManager.get_client", AsyncMock(return_value=paperless)), \
         patch.object(DocumentProcessor, "process_document", side_effect=process_one), \
         patch.object(DocumentProcessor, "_get_modular_tag_map", AsyncMock(return_value={"title": "ai-title"})), \
         patch.object(DocumentProcessor, "_get_config", AsyncMock(return_value="ai-process")), \
         patch("app.services.scheduler.get_max_concurrent_processing", AsyncMock(return_value=1)), \
         patch("app.services.scheduler.get_max_consecutive_failures", AsyncMock(return_value=0)):
        result = await scheduler.process_modular_tagged_documents()
    assert calls == [1]
    assert scheduler._load_state()["last_stop"]["kind"] == "review_tag"
    assert scheduler._load_state()["last_stop"]["reason"] == STOP["error"]
    assert result["processed"] == 0


@pytest.mark.asyncio
async def test_the_scheduled_run_skips_the_modular_pass_after_the_stop():
    with patch("app.services.scheduler.process_tagged_documents", AsyncMock(return_value={"processed": 0, "stop": {"reason": "x", "kind": "review_tag"}})) as legacy, \
         patch("app.services.scheduler.process_modular_tagged_documents", AsyncMock(return_value={"processed": 0})) as modular:
        await scheduler.process_documents_task()
    legacy.assert_awaited_once()
    modular.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_scheduled_run_ends_after_the_stop():
    """Skipping the modular pass must not skip clearing the run as well."""
    seen = []

    async def legacy():
        seen.append(scheduler.get_scheduler_status()["is_processing"])
        return {"processed": 0, "stop": {"reason": "x", "kind": "review_tag"}}

    with patch("app.services.scheduler.process_tagged_documents", AsyncMock(side_effect=legacy)), \
         patch("app.services.scheduler.process_modular_tagged_documents", AsyncMock(return_value={"processed": 0})):
        await scheduler.process_documents_task()
    assert seen == [True]
    assert scheduler.get_scheduler_status()["is_processing"] is False


def test_the_trigger_route_skips_the_modular_pass_and_reports_the_stop(client):
    with patch("app.routers.documents.process_tagged_with_state", AsyncMock(return_value={"processed": 0, "failed": 1, "results": [STOP], "stop": {"reason": STOP["error"], "kind": "review_tag"}})), \
         patch("app.routers.documents.process_modular_with_state", AsyncMock()) as modular, \
         patch("app.routers.documents.try_trigger_processing", return_value=(True, "")):
        r = client.post("/api/documents/trigger")
    modular.assert_not_awaited()
    assert r.json()["stop"] == {"reason": STOP["error"], "kind": "review_tag"}


def test_a_failure_breaker_stop_still_runs_the_modular_pass(client):
    breaker = {"reason": "provider unavailable", "kind": "failures"}
    with patch("app.routers.documents.process_tagged_with_state", AsyncMock(return_value={"processed": 0, "failed": 3, "results": [], "stop": breaker})), \
         patch("app.routers.documents.process_modular_with_state", AsyncMock(return_value={"processed": 1, "failed": 0, "results": [OK]})) as modular, \
         patch("app.routers.documents.try_trigger_processing", return_value=(True, "")):
        r = client.post("/api/documents/trigger")
    modular.assert_awaited_once()
    body = r.json()
    assert body["processed"] == 1
    assert body["failed"] == 3
    assert body["stop"] == breaker


@pytest.mark.asyncio
async def test_the_automation_run_skips_the_modular_pass_after_the_stop(monkeypatch, tmp_path):
    from app.services import automation

    monkeypatch.setattr(automation, "LAST_RESULT_FILE", str(tmp_path / "automation_last_result.json"))
    legacy_result = {"processed": 0, "failed": 1, "results": [STOP], "stop": {"reason": STOP["error"], "kind": "review_tag"}}
    try:
        with patch("app.services.automation.process_tagged_documents", AsyncMock(return_value=legacy_result)), \
             patch("app.services.automation.process_modular_tagged_documents", AsyncMock()) as modular:
            await automation._run_process_all()
        last_result = automation.get_automation_status()["last_result"]
    finally:
        automation._last_result = None
    modular.assert_not_awaited()
    assert last_result["stop"] == {"reason": STOP["error"], "kind": "review_tag"}
    assert last_result["success"] is False


def test_a_hand_stop_and_the_failure_breaker_keep_their_kinds():
    scheduler.record_run_stop(scheduler.HAND_STOP_REASON, 0)
    assert scheduler._load_state()["last_stop"]["kind"] == "hand"
    scheduler.record_run_stop("provider unavailable", 3)
    assert scheduler._load_state()["last_stop"]["kind"] == "failures"


def test_a_recorded_review_stop_is_not_overwritten_by_the_hand_flag():
    scheduler._set_processing()
    scheduler.record_run_stop("Review tag 'ai-review' does not exist in Paperless", 0, kind="review_tag")
    scheduler.request_run_stop()
    stop = {"reason": "Review tag 'ai-review' does not exist in Paperless", "failures": 0, "kind": "review_tag"}
    # The modular loop's helper must keep what is already recorded.
    assert scheduler._note_hand_stop_for_tests(stop) is True
    assert stop["kind"] == "review_tag"


def test_the_status_passes_the_kind_through(client):
    scheduler.record_run_stop("Review tag 'ai-review' does not exist in Paperless", 0, kind="review_tag")
    body = client.get("/api/scheduler").json()
    assert body["last_stop"]["kind"] == "review_tag"
