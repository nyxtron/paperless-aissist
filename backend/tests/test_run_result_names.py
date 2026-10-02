"""The run result names what it wrote, including a correspondent the run created.

The names come from the lists fetched before the steps, so a correspondent
created during the run used to show as "corr:<id>" in the Process panel.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import select

from app.database import get_session
from app.models import ProcessingLog
from app.services.processor import DocumentProcessor
from app.services.steps.base import StepResult

DOC_ID = 4711
TAGS = [{"id": 1, "name": "ai-process"}, {"id": 2, "name": "ai-processed"}]


@pytest.fixture
def clean_log(client):
    yield
    with get_session() as session:
        for row in session.exec(select(ProcessingLog).where(ProcessingLog.document_id == DOC_ID)):
            session.delete(row)


def _processor(mock_paperless, mock_llm, step_result):
    mock_llm.provider, mock_llm.model = "ollama", "qwen2.5:7b"
    mock_llm.complete = AsyncMock(return_value={"text": ""})
    mock_paperless.get_document = AsyncMock(
        return_value={"id": DOC_ID, "title": "Scan", "content": "Rechnung Nadine-Fotogenial", "tags": [1]}
    )
    step = MagicMock()
    step.name = "correspondent"
    step.can_handle.return_value = True
    step.execute = AsyncMock(return_value=step_result)
    step.update_metadata = AsyncMock()

    processor = DocumentProcessor(paperless=mock_paperless)
    processor._build_steps = AsyncMock(return_value=[step])
    processor._get_config_dict = AsyncMock(return_value={"modular_tag_process": "ai-process"})
    processor._get_config = AsyncMock(
        side_effect=lambda key, default=None: {"process_tag": "ai-process", "processed_tag": "ai-processed"}.get(key, default)
    )
    processor._fetch_metadata = AsyncMock(
        return_value={
            "tags": TAGS,
            "correspondents": [{"id": 9, "name": "AOK"}],
            "document_types": [],
            "custom_fields": [],
        }
    )
    processor._apply_metadata_update = AsyncMock()
    processor._apply_tag_updates = AsyncMock()
    return processor


async def _run(processor, mock_llm):
    with patch("app.services.processor.LLMHandlerManager.get_handler", AsyncMock(return_value=mock_llm)):
        return await processor.process_document(DOC_ID)


@pytest.mark.asyncio
async def test_a_correspondent_created_in_the_run_is_named(clean_log, mock_paperless, mock_llm):
    created = StepResult(
        data={"correspondent": 77},
        details={"created_correspondent": {"id": 77, "name": "Nadine-Fotogenial"}},
    )
    result = await _run(_processor(mock_paperless, mock_llm, created), mock_llm)
    assert result["success"] is True, result.get("error")
    assert result["proposed_changes"]["correspondent"] == {"id": 77, "name": "Nadine-Fotogenial"}


@pytest.mark.asyncio
async def test_an_existing_correspondent_is_named_as_before(clean_log, mock_paperless, mock_llm):
    result = await _run(_processor(mock_paperless, mock_llm, StepResult(data={"correspondent": 9})), mock_llm)
    assert result["proposed_changes"]["correspondent"] == {"id": 9, "name": "AOK"}


@pytest.mark.asyncio
async def test_a_correspondent_another_document_created_is_named(clean_log, mock_paperless, mock_llm):
    # Two documents of one batch from the same new sender: the other one created it.
    mock_paperless.get_correspondents = AsyncMock(
        return_value=[{"id": 9, "name": "AOK"}, {"id": 99, "name": "Neue GmbH"}]
    )
    result = await _run(_processor(mock_paperless, mock_llm, StepResult(data={"correspondent": 99})), mock_llm)
    assert result["proposed_changes"]["correspondent"] == {"id": 99, "name": "Neue GmbH"}
    mock_paperless.get_correspondents.assert_awaited_with(force_refresh=True)


@pytest.mark.asyncio
async def test_a_failed_refresh_leaves_the_result_as_it_was(clean_log, mock_paperless, mock_llm):
    mock_paperless.get_correspondents = AsyncMock(side_effect=RuntimeError("Paperless gone"))
    result = await _run(_processor(mock_paperless, mock_llm, StepResult(data={"correspondent": 99})), mock_llm)
    assert result["success"] is True, result.get("error")
    assert result["proposed_changes"]["correspondent"] == {"id": 99, "name": "corr:99"}
