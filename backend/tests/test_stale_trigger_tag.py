"""A document that lost its trigger tag while queued is left alone (issue #43, #47).

The batch list is a snapshot. Nothing re-checked the tags once a document's turn
came, so a document whose tag had been removed in the meantime was still written
to, given the processed tag, and logged as a successful run.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.processor import DocumentProcessor


def _processor(mock_paperless, handled: bool):
    step = MagicMock()
    step.name = "title"
    step.can_handle.return_value = handled
    step.execute = AsyncMock()
    step.update_metadata = AsyncMock()

    processor = DocumentProcessor(paperless=mock_paperless)
    processor._build_steps = AsyncMock(return_value=[step])
    processor._get_config_dict = AsyncMock(
        return_value={"modular_tag_process": "ai-process"}
    )
    processor._get_config = AsyncMock(
        side_effect=lambda key, default=None: {
            "process_tag": "ai-process",
            "processed_tag": "ai-processed",
        }.get(key, default)
    )
    processor._log_processing = AsyncMock(return_value=123)
    processor._delete_log = AsyncMock()
    processor._apply_metadata_update = AsyncMock()
    processor._apply_tag_updates = AsyncMock()
    processor._fetch_metadata = AsyncMock(
        return_value={
            "tags": [{"id": 1, "name": "ai-process"}],
            "correspondents": [],
            "document_types": [],
            "custom_fields": [],
        }
    )
    return processor, step


@pytest.mark.asyncio
async def test_a_document_without_a_trigger_tag_is_skipped(mock_paperless, mock_llm):
    mock_paperless.get_document = AsyncMock(
        return_value={"id": 1, "title": "Invoice", "content": "x", "tags": []}
    )
    processor, step = _processor(mock_paperless, handled=False)

    with patch(
        "app.services.processor.LLMHandlerManager.get_handler",
        AsyncMock(return_value=mock_llm),
    ):
        result = await processor.process_document(1)

    assert result["skipped"] is True
    step.execute.assert_not_awaited()
    # Nothing was written and the tags were left exactly as they are.
    processor._apply_metadata_update.assert_not_awaited()
    processor._apply_tag_updates.assert_not_awaited()
    # No log row either, so a skip does not show up as a processed document.
    processor._log_processing.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_document_that_still_has_its_tag_runs(mock_paperless, mock_llm):
    mock_llm.provider = "test-provider"
    mock_llm.model = "test-model"
    mock_paperless.get_document = AsyncMock(
        return_value={"id": 1, "title": "Invoice", "content": "x", "tags": [1]}
    )
    processor, step = _processor(mock_paperless, handled=True)
    from app.services.steps.base import StepResult

    step.execute = AsyncMock(return_value=StepResult(data={"title": "New"}))

    with patch(
        "app.services.processor.LLMHandlerManager.get_handler",
        AsyncMock(return_value=mock_llm),
    ):
        result = await processor.process_document(1)

    assert not result.get("skipped")
    step.execute.assert_awaited()


@pytest.mark.asyncio
async def test_a_skip_counts_as_neither_processed_nor_failed(mock_paperless):
    """Otherwise a batch of skips reports itself as a batch of failures."""
    mock_paperless.get_tags = AsyncMock(return_value=[{"id": 1, "name": "ai-process"}])
    mock_paperless.list_documents = AsyncMock(
        return_value=[{"id": 1}, {"id": 2}, {"id": 3}]
    )
    mock_paperless.reset_metrics = MagicMock()
    mock_paperless.get_metrics = MagicMock(
        return_value={"requests": 0, "paged_requests": 0}
    )
    processor = DocumentProcessor(paperless=mock_paperless)
    processor._get_config = AsyncMock(return_value="ai-process")
    processor.process_document = AsyncMock(
        side_effect=[
            {"success": True},
            {"success": True, "skipped": True},
            {"success": False},
        ]
    )

    result = await processor.process_tagged_documents()

    assert result["processed"] == 1
    assert result["failed"] == 1
    assert result["success"] is False


@pytest.mark.asyncio
async def test_the_modular_batch_also_keeps_skips_out_of_both_counts(mock_paperless):
    """The modular path has its own tally, and it drifted from the legacy one."""
    from app.services import scheduler as scheduler_service

    mock_paperless.reset_metrics = MagicMock()
    mock_paperless.get_metrics = MagicMock(
        return_value={"requests": 0, "paged_requests": 0}
    )
    mock_paperless.get_tags = AsyncMock(
        return_value=[{"id": 7, "name": "ai-title"}, {"id": 8, "name": "ai-process"}]
    )
    mock_paperless.list_documents = AsyncMock(
        return_value=[{"id": 1}, {"id": 2}, {"id": 3}]
    )

    per_doc = {
        1: {"success": True},
        2: {"success": True, "skipped": True},
        3: {"success": False, "error": "boom"},
    }

    with (
        patch(
            "app.services.paperless_manager.PaperlessClientManager.get_client",
            AsyncMock(return_value=mock_paperless),
        ),
        patch.object(
            DocumentProcessor,
            "_get_modular_tag_map",
            AsyncMock(return_value={"modular_tag_title": "ai-title"}),
        ),
        patch.object(DocumentProcessor, "_get_config", AsyncMock(return_value="ai-process")),
        patch.object(
            DocumentProcessor,
            "process_document",
            AsyncMock(side_effect=lambda doc_id: per_doc[doc_id]),
        ),
    ):
        result = await scheduler_service.process_modular_tagged_documents()

    # Without the filter the skipped document would be counted as work done.
    assert result["processed"] == 1
