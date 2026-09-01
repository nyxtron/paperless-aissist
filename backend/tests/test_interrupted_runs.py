"""An interrupted run must not leave a document stuck at processing (#43, #49).

The log row is written as "processing" when a document starts and only rewritten
when the run ends. A restart mid-batch left it saying processing for good, and
the dashboard kept showing that document as busy — the scheduler clears its own
state file on startup, but nothing touched the row.
"""

import pytest
from sqlmodel import select

from app.database import get_session
from app.models import ProcessingLog
from app.services.processor import close_interrupted_runs


@pytest.fixture(autouse=True)
def _clean_log(client):
    """The suite shares one database, so start each case with an empty log."""
    with get_session() as session:
        for row in session.exec(select(ProcessingLog)):
            session.delete(row)
    yield


def _add(status: str, doc_id: int) -> None:
    with get_session() as session:
        session.add(
            ProcessingLog(document_id=doc_id, document_title=f"Doc {doc_id}", status=status)
        )


def _statuses() -> dict[int, str]:
    with get_session() as session:
        return {row.document_id: row.status for row in session.exec(select(ProcessingLog))}


def test_a_stranded_row_is_settled():
    _add("processing", 11608)

    assert close_interrupted_runs() == 1
    assert _statuses()[11608] == "failed"


def test_finished_rows_are_left_alone():
    _add("success", 1)
    _add("failed", 2)
    _add("skipped", 3)

    assert close_interrupted_runs() == 0
    assert _statuses() == {1: "success", 2: "failed", 3: "skipped"}


def test_the_reason_says_what_happened():
    _add("processing", 42)
    close_interrupted_runs()

    with get_session() as session:
        message = session.exec(select(ProcessingLog)).first().error_message

    assert "interrupted" in (message or "").lower()


def test_it_is_harmless_with_nothing_to_do():
    assert close_interrupted_runs() == 0


def test_startup_settles_them():
    """Direct calls prove nothing if nothing calls it when the app comes up."""
    from fastapi.testclient import TestClient

    from app.main import app

    _add("processing", 999)

    with TestClient(app):
        pass

    assert _statuses()[999] == "failed"
