"""Documents are started in the order the Process list shows (issue #43, #44).

The modular batch deduped the fetched documents into a set, so the run handed
them out in hash order. On a large batch that looks random next to the list,
which is sorted by creation date.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import scheduler as scheduler_service
from app.services.paperless import PaperlessClient
from app.services.processor import DocumentProcessor

# Ids picked so that set iteration reorders them: {5, 12, 3, 40, 21} does not
# iterate in this sequence, which is what made the old code look random.
LIST_ORDER = [5, 12, 3, 40, 21]


@pytest.mark.asyncio
async def test_documents_are_started_in_list_order(mock_paperless):
    mock_paperless.reset_metrics = MagicMock()
    mock_paperless.get_metrics = MagicMock(
        return_value={"requests": 0, "paged_requests": 0}
    )
    mock_paperless.get_tags = AsyncMock(return_value=[{"id": 7, "name": "ai-title"}])
    mock_paperless.list_documents = AsyncMock(
        return_value=[{"id": i} for i in LIST_ORDER]
    )

    started: list[int] = []

    async def record(doc_id):
        started.append(doc_id)
        return {"success": True}

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
        patch.object(
            DocumentProcessor, "_get_config", AsyncMock(return_value="ai-process")
        ),
        patch.object(DocumentProcessor, "process_document", AsyncMock(side_effect=record)),
        patch.object(
            scheduler_service, "get_max_concurrent_processing", AsyncMock(return_value=1)
        ),
    ):
        await scheduler_service.process_modular_tagged_documents()

    assert started == LIST_ORDER


@pytest.mark.asyncio
async def test_duplicates_are_still_collapsed(mock_paperless):
    """A document carrying two trigger tags is returned twice but runs once."""
    mock_paperless.reset_metrics = MagicMock()
    mock_paperless.get_metrics = MagicMock(
        return_value={"requests": 0, "paged_requests": 0}
    )
    mock_paperless.get_tags = AsyncMock(return_value=[{"id": 7, "name": "ai-title"}])
    mock_paperless.list_documents = AsyncMock(
        return_value=[{"id": 5}, {"id": 12}, {"id": 5}]
    )

    started: list[int] = []

    async def record(doc_id):
        started.append(doc_id)
        return {"success": True}

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
        patch.object(
            DocumentProcessor, "_get_config", AsyncMock(return_value="ai-process")
        ),
        patch.object(DocumentProcessor, "process_document", AsyncMock(side_effect=record)),
        patch.object(
            scheduler_service, "get_max_concurrent_processing", AsyncMock(return_value=1)
        ),
    ):
        await scheduler_service.process_modular_tagged_documents()

    assert started == [5, 12]


@pytest.mark.asyncio
async def test_the_query_pins_the_order_instead_of_trusting_the_server():
    client = PaperlessClient(base_url="http://paperless.test", token="t")
    client._get_fetch_size = AsyncMock(return_value=100)
    client._get_max_pages = AsyncMock(return_value=1)
    client._get_all_pages = AsyncMock(return_value=[])

    await client.list_documents(tags_any=[7])

    url = client._get_all_pages.await_args.args[0]
    assert "ordering=-created" in url
