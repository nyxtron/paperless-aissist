import pytest
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

os.environ["DATA_DIR"] = tempfile.mkdtemp()

from fastapi.testclient import TestClient
from app.main import app
from app.database import get_session, create_db_and_tables
from app.services.steps.base import StepContext

create_db_and_tables()


@pytest.fixture(name="client")
def client_fixture():
    with TestClient(app) as c:
        yield c


@pytest.fixture(name="session")
def session_fixture():
    with get_session() as session:
        yield session


@pytest.fixture
def mock_paperless():
    p = AsyncMock()
    p.get_document = AsyncMock(
        return_value={
            "id": 1,
            "title": "Test Document",
            "content": "Sample invoice content for testing.",
            "tags": [5, 10],
            "custom_fields": [],
        }
    )
    p.get_correspondents = AsyncMock(
        return_value=[
            {"id": 1, "name": "Amazon"},
            {"id": 2, "name": "BAUHAUS"},
            {"id": 3, "name": "HORNBACH"},
        ]
    )
    p.get_document_types = AsyncMock(
        return_value=[
            {"id": 1, "name": "Invoice"},
            {"id": 2, "name": "Contract"},
        ]
    )
    p.get_tags = AsyncMock(
        return_value=[
            {"id": 1, "name": "Amazon"},
            {"id": 2, "name": "BAUHAUS"},
            {"id": 5, "name": "ai-process"},
            {"id": 6, "name": "inbox"},
            {"id": 10, "name": "reviewed"},
        ]
    )
    p.get_custom_fields = AsyncMock(
        return_value=[
            {"id": 1, "name": "Invoice Number"},
            {"id": 2, "name": "Amount"},
            {"id": 3, "name": "Date"},
        ]
    )
    p.get_document_file = AsyncMock(return_value=b"fake pdf bytes")
    p.update_document = AsyncMock(return_value={})
    return p


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value={"text": "", "raw": ""})
    return llm


@pytest.fixture
def mock_ctx(mock_paperless, mock_llm):
    return StepContext(
        doc_id=1,
        paperless=mock_paperless,
        llm=mock_llm,
        config={
            "modular_tag_process": "ai-process",
            "modular_tag_title": "ai-title",
            "modular_tag_correspondent": "ai-correspondent",
            "modular_tag_document_type": "ai-document-type",
            "modular_tag_tags": "ai-tags",
            "modular_tag_fields": "ai-fields",
            "modular_tag_ocr": "ai-ocr",
            "modular_tag_ocr_fix": "ai-ocr-fix",
            "force_ocr_tag": "force_ocr",
            "force_ocr_fix_tag": "force-ocr-fix",
            "enable_vision": "false",
            "ocr_post_process": "false",
            "tag_blacklist": "reviewed",
        },
        trigger_tags={"ai-process"},
        ocr_text=None,
    )


@pytest.fixture
def mock_prompt_model():
    from app.models import Prompt

    mock_prompt = MagicMock(spec=Prompt)
    mock_prompt.system_prompt = "You are a document analyzer."
    mock_prompt.user_template = "Content: {content}"
    mock_prompt.is_active = True
    mock_prompt.prompt_type = None

    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(
        return_value=MagicMock(first=MagicMock(return_value=mock_prompt))
    )
    return mock_session
