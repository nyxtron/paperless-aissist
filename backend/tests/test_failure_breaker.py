"""A batch gives up when the provider keeps failing (issue #43, #46).

Fifty tagged documents against a dead provider used to mean fifty attempts and
fifty failures: the concurrency limit caps how many run at once, it never stops
the queue. Only provider failures count towards the limit — one unreadable PDF
must not end a healthy run.
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import LLMError, LLMUnavailableError
from app.services import scheduler as scheduler_service
from app.services.processor import DocumentProcessor


def test_only_provider_failures_count():
    assert scheduler_service.is_provider_failure({"retryable": True}) is True
    assert scheduler_service.is_provider_failure({"provider_failure": True}) is True
    assert scheduler_service.is_provider_failure(LLMUnavailableError("down")) is True
    assert scheduler_service.is_provider_failure(LLMError("refused")) is True
    # A document that simply failed is not a reason to stop the run.
    assert scheduler_service.is_provider_failure({"success": False}) is False
    assert scheduler_service.is_provider_failure(ValueError("bad pdf")) is False
    assert scheduler_service.is_provider_failure({"success": True}) is False


def _batch(mock_paperless, per_doc, doc_ids, limit):
    mock_paperless.reset_metrics = MagicMock()
    mock_paperless.get_metrics = MagicMock(
        return_value={"requests": 0, "paged_requests": 0}
    )
    mock_paperless.get_tags = AsyncMock(return_value=[{"id": 7, "name": "ai-title"}])
    mock_paperless.list_documents = AsyncMock(
        return_value=[{"id": i} for i in doc_ids]
    )
    attempted: list[int] = []

    async def record(doc_id):
        attempted.append(doc_id)
        return per_doc(doc_id)

    ctx = [
        patch(
            "app.services.paperless_manager.PaperlessClientManager.get_client",
            AsyncMock(return_value=mock_paperless),
        ),
        patch.object(
            DocumentProcessor,
            "_get_modular_tag_map",
            AsyncMock(return_value={"modular_tag_title": "ai-title"}),
        ),
        patch.object(
            DocumentProcessor, "_get_config", AsyncMock(return_value="ai-process")
        ),
        patch.object(DocumentProcessor, "process_document", AsyncMock(side_effect=record)),
        patch.object(
            scheduler_service, "get_max_concurrent_processing", AsyncMock(return_value=1)
        ),
        patch.object(
            scheduler_service,
            "get_max_consecutive_failures",
            AsyncMock(return_value=limit),
        ),
    ]
    return attempted, ctx


async def _run(ctx):
    with ExitStack() as stack:
        for cm in ctx:
            stack.enter_context(cm)
        await scheduler_service.process_modular_tagged_documents()


@pytest.mark.asyncio
async def test_a_dead_provider_ends_the_run(mock_paperless, tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_service, "record_run_stop", MagicMock())
    attempted, ctx = _batch(
        mock_paperless,
        lambda _: {"success": False, "retryable": True, "error": "provider down"},
        list(range(1, 21)),
        limit=3,
    )

    await _run(ctx)

    assert len(attempted) == 3, f"stopped after {len(attempted)} of 20"
    scheduler_service.record_run_stop.assert_called_once()


@pytest.mark.asyncio
async def test_bad_documents_do_not_end_the_run(mock_paperless, monkeypatch):
    """Three unreadable PDFs in a row must not stop a healthy provider."""
    monkeypatch.setattr(scheduler_service, "record_run_stop", MagicMock())
    attempted, ctx = _batch(
        mock_paperless,
        lambda _: {"success": False, "error": "could not read pdf"},
        list(range(1, 11)),
        limit=3,
    )

    await _run(ctx)

    assert len(attempted) == 10
    scheduler_service.record_run_stop.assert_not_called()


@pytest.mark.asyncio
async def test_a_success_in_between_resets_the_count(mock_paperless, monkeypatch):
    monkeypatch.setattr(scheduler_service, "record_run_stop", MagicMock())
    # fail, fail, succeed, fail, fail -> never three in a row
    outcomes = {
        1: {"success": False, "retryable": True},
        2: {"success": False, "retryable": True},
        3: {"success": True},
        4: {"success": False, "retryable": True},
        5: {"success": False, "retryable": True},
    }
    attempted, ctx = _batch(mock_paperless, lambda d: outcomes[d], [1, 2, 3, 4, 5], limit=3)

    await _run(ctx)

    assert len(attempted) == 5
    scheduler_service.record_run_stop.assert_not_called()


@pytest.mark.asyncio
async def test_zero_disables_the_breaker(mock_paperless, monkeypatch):
    monkeypatch.setattr(scheduler_service, "record_run_stop", MagicMock())
    attempted, ctx = _batch(
        mock_paperless,
        lambda _: {"success": False, "retryable": True},
        list(range(1, 9)),
        limit=0,
    )

    await _run(ctx)

    assert len(attempted) == 8
    scheduler_service.record_run_stop.assert_not_called()


@pytest.mark.asyncio
async def test_the_legacy_loop_stops_too(mock_paperless, monkeypatch):
    """The ai-process path is a separate loop and needs its own brake."""
    monkeypatch.setattr(scheduler_service, "record_run_stop", MagicMock())
    mock_paperless.reset_metrics = MagicMock()
    mock_paperless.get_metrics = MagicMock(
        return_value={"requests": 0, "paged_requests": 0}
    )
    mock_paperless.get_tags = AsyncMock(return_value=[{"id": 1, "name": "ai-process"}])
    mock_paperless.list_documents = AsyncMock(
        return_value=[{"id": i} for i in range(1, 21)]
    )

    attempted: list[int] = []

    async def record(doc_id):
        attempted.append(doc_id)
        return {"success": False, "retryable": True, "error": "provider down"}

    processor = DocumentProcessor(paperless=mock_paperless)
    processor._get_config = AsyncMock(return_value="ai-process")
    processor.process_document = AsyncMock(side_effect=record)

    with patch.object(
        scheduler_service, "get_max_consecutive_failures", AsyncMock(return_value=3)
    ):
        await processor.process_tagged_documents()

    assert len(attempted) == 3, f"stopped after {len(attempted)} of 20"
    scheduler_service.record_run_stop.assert_called_once()
