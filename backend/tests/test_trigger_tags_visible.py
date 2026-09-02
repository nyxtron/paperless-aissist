"""Which tags triggered a run is recorded and handed to the UI (#43, #48).

The tags were known while a document ran but were never stored, so the dashboard
could not say afterwards what a run had been asked to do. The document list had
tag ids without names, so it could not say it either.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import select

from app.database import get_session
from app.models import ProcessingLog
from app.services.processor import DocumentProcessor


@pytest.fixture(autouse=True)
def _clean_log(client):
    with get_session() as session:
        for row in session.exec(select(ProcessingLog)):
            session.delete(row)
    yield


class TestTheLogRemembersThem:
    @pytest.mark.asyncio
    async def test_they_are_stored_on_the_row(self, mock_paperless):
        processor = DocumentProcessor(paperless=mock_paperless)

        log_id = await processor._log_processing(
            doc_id=7,
            doc_title="Invoice",
            status="success",
            provider="ollama",
            model="qwen",
            llm_response=None,
            error_message=None,
            processing_time_ms=120,
            trigger_tags=["ai-ocr", "ai-title"],
        )

        with get_session() as session:
            stored = session.exec(
                select(ProcessingLog).where(ProcessingLog.id == log_id)
            ).first().trigger_tags

        assert stored == "ai-ocr, ai-title"

    @pytest.mark.asyncio
    async def test_no_tags_leaves_the_column_empty(self, mock_paperless):
        processor = DocumentProcessor(paperless=mock_paperless)

        log_id = await processor._log_processing(
            doc_id=8,
            doc_title="Invoice",
            status="success",
            provider=None,
            model=None,
            llm_response=None,
            error_message=None,
            processing_time_ms=1,
            trigger_tags=[],
        )

        with get_session() as session:
            stored = session.exec(
                select(ProcessingLog).where(ProcessingLog.id == log_id)
            ).first().trigger_tags

        assert stored is None

    @pytest.mark.asyncio
    async def test_they_are_filled_in_when_the_run_finishes(self, mock_paperless):
        """The real path: the row is opened before the tags are known.

        A row is written as "processing" the moment a document starts, and only
        rewritten at the end. If the update branch ignored the tags, nothing
        would ever carry them in practice however well the insert worked.
        """
        processor = DocumentProcessor(paperless=mock_paperless)

        log_id = await processor._log_processing(
            doc_id=11,
            doc_title="Invoice",
            status="processing",
            provider=None,
            model=None,
            llm_response=None,
            error_message=None,
            processing_time_ms=0,
        )

        await processor._log_processing(
            doc_id=11,
            doc_title="Invoice",
            status="success",
            provider="ollama",
            model="qwen",
            llm_response=None,
            error_message=None,
            processing_time_ms=900,
            trigger_tags=["ai-fields"],
            log_id=log_id,
        )

        with get_session() as session:
            row = session.exec(
                select(ProcessingLog).where(ProcessingLog.id == log_id)
            ).first()
            stored, status = row.trigger_tags, row.status

        assert stored == "ai-fields"
        assert status == "success"

    def test_the_dashboard_endpoint_returns_them(self, client):
        with get_session() as session:
            session.add(
                ProcessingLog(
                    document_id=9,
                    document_title="Invoice",
                    status="success",
                    trigger_tags="ai-ocr",
                )
            )

        response = client.get("/api/stats/recent?limit=5")

        assert response.status_code == 200
        assert response.json()[0]["trigger_tags"] == "ai-ocr"


def test_the_document_list_carries_tag_names(client):
    """Ids alone cannot tell a user which trigger a document is waiting on."""
    paperless = AsyncMock()
    paperless.base_url = "http://paperless.test"
    paperless.get_tags = AsyncMock(
        return_value=[{"id": 5, "name": "ai-ocr"}, {"id": 6, "name": "inbox"}]
    )
    paperless.list_documents = AsyncMock(
        return_value=[
            {"id": 1, "title": "Invoice", "created": "", "added": "", "tags": [5, 6, 99]}
        ]
    )
    paperless.get_metrics = MagicMock(return_value={"requests": 0, "paged_requests": 0})
    paperless.close = AsyncMock()

    with (
        patch(
            "app.routers.documents.PaperlessClient.from_config",
            AsyncMock(return_value=paperless),
        ),
        patch.object(
            DocumentProcessor,
            "_get_modular_tag_map",
            AsyncMock(return_value={"modular_tag_ocr": "ai-ocr"}),
        ),
    ):
        response = client.get("/api/documents/tagged")

    assert response.status_code == 200
    doc = response.json()["documents"][0]
    # 99 is unknown to Paperless and is dropped rather than guessed at.
    assert doc["tag_names"] == ["ai-ocr", "inbox"]
    assert doc["tags"] == [5, 6, 99]
