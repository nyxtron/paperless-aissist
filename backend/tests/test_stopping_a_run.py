"""A batch can be asked to stop from the page (issue #54).

Until now a run could only be waited out: the failure breaker ended one when
the provider kept refusing, but a person who had started a batch with the wrong
prompt had to sit it out or restart the container. The request is read between
documents, so whatever is in flight is always finished, and it ends the current
run only — the scheduler keeps its interval and picks the rest up next tick.
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import scheduler as scheduler_service
from app.services.processor import DocumentProcessor


def _idle():
    scheduler_service._clear_processing()
    scheduler_service._save_state(scheduler_service._default_state())


class TestTheRequestItself:
    def test_nothing_is_running_so_there_is_nothing_to_stop(self):
        _idle()

        assert scheduler_service.request_run_stop() is False
        assert scheduler_service.is_run_stop_requested() is False

    def test_a_running_batch_takes_the_request(self):
        _idle()
        scheduler_service._set_processing()

        assert scheduler_service.request_run_stop() is True
        assert scheduler_service.is_run_stop_requested() is True
        assert scheduler_service.get_scheduler_status()["stop_requested"] is True

    def test_a_new_run_is_not_born_stopped(self):
        """The request belongs to the run it was made for."""
        _idle()
        scheduler_service._set_processing()
        scheduler_service.request_run_stop()

        scheduler_service._set_processing()

        assert scheduler_service.is_run_stop_requested() is False

    def test_the_request_is_spent_when_the_run_ends(self):
        _idle()
        scheduler_service._set_processing()
        scheduler_service.request_run_stop()

        scheduler_service._clear_processing()

        assert scheduler_service.is_run_stop_requested() is False
        assert scheduler_service.get_scheduler_status()["stop_requested"] is False

    def test_a_state_file_from_before_reports_no_request(self):
        _idle()
        state = scheduler_service._load_state()
        state.pop("stop_requested", None)
        scheduler_service._save_state(state)

        assert scheduler_service.is_run_stop_requested() is False


@pytest.fixture
def _clean_state():
    _idle()
    yield
    _idle()


class TestTheLoopsHonourIt:
    @pytest.mark.asyncio
    async def test_the_legacy_loop_stops_after_the_document_in_flight(
        self, mock_paperless, _clean_state
    ):
        mock_paperless.reset_metrics = MagicMock()
        mock_paperless.get_metrics = MagicMock(
            return_value={"requests": 0, "paged_requests": 0}
        )
        mock_paperless.get_tags = AsyncMock(
            return_value=[{"id": 1, "name": "ai-process"}]
        )
        mock_paperless.list_documents = AsyncMock(
            return_value=[{"id": i} for i in range(1, 21)]
        )
        scheduler_service._set_processing()

        attempted: list[int] = []

        async def record(doc_id):
            attempted.append(doc_id)
            # Asked while this document is being worked on.
            scheduler_service.request_run_stop()
            return {"success": True}

        processor = DocumentProcessor(paperless=mock_paperless)
        processor._get_config = AsyncMock(return_value="ai-process")
        processor.process_document = AsyncMock(side_effect=record)

        with patch.object(
            scheduler_service, "get_max_consecutive_failures", AsyncMock(return_value=3)
        ):
            await processor.process_tagged_documents()

        assert attempted == [1], f"worked through {len(attempted)} of 20"
        last_stop = scheduler_service.get_scheduler_status()["last_stop"]
        assert last_stop["reason"] == scheduler_service.HAND_STOP_REASON
        assert last_stop["failures"] == 0

    @pytest.mark.asyncio
    async def test_the_modular_loop_lets_queued_documents_bow_out(
        self, mock_paperless, _clean_state
    ):
        mock_paperless.reset_metrics = MagicMock()
        mock_paperless.get_metrics = MagicMock(
            return_value={"requests": 0, "paged_requests": 0}
        )
        mock_paperless.get_tags = AsyncMock(
            return_value=[{"id": 7, "name": "ai-title"}]
        )
        mock_paperless.list_documents = AsyncMock(
            return_value=[{"id": i} for i in range(1, 21)]
        )
        scheduler_service._set_processing()

        attempted: list[int] = []

        async def record(doc_id):
            attempted.append(doc_id)
            scheduler_service.request_run_stop()
            return {"success": True}

        with ExitStack() as stack:
            for cm in [
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
                patch.object(
                    DocumentProcessor, "process_document", AsyncMock(side_effect=record)
                ),
                patch.object(
                    scheduler_service,
                    "get_max_concurrent_processing",
                    AsyncMock(return_value=1),
                ),
                patch.object(
                    scheduler_service,
                    "get_max_consecutive_failures",
                    AsyncMock(return_value=3),
                ),
            ]:
                stack.enter_context(cm)
            await scheduler_service.process_modular_tagged_documents()

        assert attempted == [1], f"worked through {len(attempted)} of 20"
        last_stop = scheduler_service.get_scheduler_status()["last_stop"]
        assert last_stop["reason"] == scheduler_service.HAND_STOP_REASON
        assert last_stop["failures"] == 0

    @pytest.mark.asyncio
    async def test_an_untouched_run_works_through_everything(
        self, mock_paperless, _clean_state
    ):
        """The brake must not engage on its own."""
        mock_paperless.reset_metrics = MagicMock()
        mock_paperless.get_metrics = MagicMock(
            return_value={"requests": 0, "paged_requests": 0}
        )
        mock_paperless.get_tags = AsyncMock(
            return_value=[{"id": 1, "name": "ai-process"}]
        )
        mock_paperless.list_documents = AsyncMock(
            return_value=[{"id": i} for i in range(1, 6)]
        )
        scheduler_service._set_processing()

        attempted: list[int] = []

        async def record(doc_id):
            attempted.append(doc_id)
            return {"success": True}

        processor = DocumentProcessor(paperless=mock_paperless)
        processor._get_config = AsyncMock(return_value="ai-process")
        processor.process_document = AsyncMock(side_effect=record)

        with patch.object(
            scheduler_service, "get_max_consecutive_failures", AsyncMock(return_value=3)
        ):
            await processor.process_tagged_documents()

        assert attempted == [1, 2, 3, 4, 5]
        assert scheduler_service.get_scheduler_status()["last_stop"] is None
