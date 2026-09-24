"""The combined classify prompt gets its lists and does not hide an outage.

The fallback runs when ai-process produced no classification. It replaced only
{content}, so the model saw the literal text "{correspondents_list}" and had to
guess names. And it caught every error: an Ollama outage during it still went
through the tag swap, marking the document processed with nothing written.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import select

from app.database import get_session
from app.exceptions import LLMError, LLMUnavailableError
from app.models import ProcessingLog, Prompt
from app.services.llm_handler import PROMPT_CUTS
from app.services.processor import DocumentProcessor
from app.services.steps.base import StepResult

TAGS = [
    {"id": 1, "name": "ai-process"},
    {"id": 2, "name": "ai-ocr"},
    {"id": 3, "name": "Steuer"},
    {"id": 4, "name": "reviewed"},
]


@pytest.fixture
def classify_prompt(client):
    with get_session() as session:
        for row in session.exec(select(ProcessingLog).where(ProcessingLog.document_id == 42)):
            session.delete(row)
        session.add(
            Prompt(
                name="classify-fallback-test",
                prompt_type="classify",
                system_prompt="Classify.",
                user_template=(
                    "Correspondents: {correspondents_list}\n"
                    "Types: {document_types_list}\n"
                    "Tags: {tags_list}\n\n{content}"
                ),
                is_active=True,
            )
        )
    yield
    with get_session() as session:
        for row in session.exec(select(Prompt).where(Prompt.name == "classify-fallback-test")):
            session.delete(row)
        for row in session.exec(select(ProcessingLog).where(ProcessingLog.document_id == 42)):
            session.delete(row)


def _processor(mock_paperless, mock_llm, reply=None, error=None):
    mock_llm.provider = "ollama"
    mock_llm.model = "qwen2.5:7b"
    if error is not None:
        mock_llm.complete = AsyncMock(side_effect=error)
    else:
        mock_llm.complete = AsyncMock(return_value={"text": reply})
    mock_paperless.get_document = AsyncMock(
        return_value={"id": 42, "title": "Scan", "content": "Beitragsbescheid", "tags": [1]}
    )

    # A step that runs but classifies nothing, so the fallback is asked.
    quiet = MagicMock()
    quiet.name = "title"
    quiet.can_handle.return_value = True
    quiet.execute = AsyncMock(return_value=StepResult(data={}))
    quiet.update_metadata = AsyncMock()

    processor = DocumentProcessor(paperless=mock_paperless)
    processor._build_steps = AsyncMock(return_value=[quiet])
    processor._get_config_dict = AsyncMock(
        return_value={"modular_tag_process": "ai-process", "tag_blacklist": "reviewed"}
    )
    processor._get_config = AsyncMock(
        side_effect=lambda key, default=None: {"process_tag": "ai-process"}.get(key, default)
    )
    processor._fetch_metadata = AsyncMock(
        return_value={
            "tags": TAGS,
            "correspondents": [{"id": 9, "name": "AOK"}],
            "document_types": [{"id": 5, "name": "Bescheid"}],
            "custom_fields": [],
        }
    )
    processor._apply_metadata_update = AsyncMock()
    processor._apply_tag_updates = AsyncMock()
    return processor


async def _run(processor, mock_llm):
    with patch(
        "app.services.processor.LLMHandlerManager.get_handler",
        AsyncMock(return_value=mock_llm),
    ):
        return await processor.process_document(42)


class TestTheListsReachTheModel:
    @pytest.mark.asyncio
    async def test_no_placeholder_is_left_and_control_tags_stay_out(
        self, classify_prompt, mock_paperless, mock_llm
    ):
        processor = _processor(mock_paperless, mock_llm, reply="Correspondent: AOK")

        await _run(processor, mock_llm)

        sent = mock_llm.complete.await_args.kwargs["user_prompt"]
        assert "{" not in sent
        assert '"AOK"' in sent and '"Bescheid"' in sent and '"Steuer"' in sent
        for name in ("ai-process", "ai-ocr", "reviewed"):
            assert f'"{name}"' not in sent, name

    @pytest.mark.asyncio
    async def test_the_answer_is_written_without_control_tags(
        self, classify_prompt, mock_paperless, mock_llm
    ):
        processor = _processor(
            mock_paperless,
            mock_llm,
            reply="Correspondent: AOK\nDocument type: Bescheid\nTags: Steuer, ai-ocr, reviewed",
        )

        result = await _run(processor, mock_llm)

        assert result["success"] is True
        processor._apply_metadata_update.assert_awaited_once_with(42, None, 9, 5)
        added = processor._apply_tag_updates.await_args.args[2]
        assert 3 in added
        assert 2 not in added and 4 not in added
        # The collector for cut prompts belongs to the call, not to what follows.
        assert PROMPT_CUTS.get() is None


class TestAnOutageIsNotSwallowed:
    @pytest.mark.asyncio
    async def test_an_unreachable_provider_leaves_the_document_for_later(
        self, classify_prompt, mock_paperless, mock_llm
    ):
        processor = _processor(mock_paperless, mock_llm, error=LLMUnavailableError("refused"))

        result = await _run(processor, mock_llm)

        assert result["success"] is False
        assert result["retryable"] is True
        processor._apply_tag_updates.assert_not_awaited()
        with get_session() as session:
            assert session.exec(
                select(ProcessingLog).where(ProcessingLog.document_id == 42)
            ).first() is None

    @pytest.mark.asyncio
    async def test_a_refusing_provider_fails_the_run(
        self, classify_prompt, mock_paperless, mock_llm
    ):
        processor = _processor(mock_paperless, mock_llm, error=LLMError("401 bad key"))

        result = await _run(processor, mock_llm)

        assert result["success"] is False
        assert result["provider_failure"] is True
        processor._apply_tag_updates.assert_not_awaited()
        with get_session() as session:
            row = session.exec(
                select(ProcessingLog).where(ProcessingLog.document_id == 42)
            ).first()
            assert row.status == "failed"

    @pytest.mark.asyncio
    async def test_any_other_failure_fails_the_run_too(
        self, classify_prompt, mock_paperless, mock_llm
    ):
        """It used to fall through to the tag swap and mark the document done."""
        processor = _processor(mock_paperless, mock_llm, error=RuntimeError("parser broke"))

        result = await _run(processor, mock_llm)

        assert result["success"] is False
        assert result.get("provider_failure") is False
        processor._apply_tag_updates.assert_not_awaited()


class TestAFailedStepComesFirst:
    @pytest.mark.asyncio
    async def test_the_combined_prompt_is_not_asked_after_a_failed_step(
        self, classify_prompt, mock_paperless, mock_llm
    ):
        """As before: a failed step ends the run, no second opinion is fetched."""
        processor = _processor(mock_paperless, mock_llm, reply="Correspondent: AOK")
        broken = MagicMock()
        broken.name = "title"
        broken.can_handle.return_value = True
        broken.execute = AsyncMock(return_value=StepResult(data={}, error="no content"))
        broken.update_metadata = AsyncMock()
        processor._build_steps = AsyncMock(return_value=[broken])

        result = await _run(processor, mock_llm)

        assert result["success"] is False
        mock_llm.complete.assert_not_awaited()
        processor._apply_tag_updates.assert_not_awaited()

