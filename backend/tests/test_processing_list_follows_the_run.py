"""The status says when a document last finished (issue #53).

The Processing page keeps its document list in a cache so it does not ask
Paperless on every visit. A run started by the scheduler swapped tags without
that cache ever hearing of it, so the list stayed stale until a browser
reload. The page now compares the cache with this timestamp.
"""

from datetime import datetime, timezone

from app.services import scheduler as scheduler_service


def _fresh_state():
    scheduler_service._clear_processing()
    scheduler_service._save_state(scheduler_service._default_state())


def test_a_fresh_state_has_no_finished_document():
    _fresh_state()

    assert scheduler_service.get_scheduler_status()["last_finished_at"] is None


def test_a_finished_document_stamps_the_moment():
    _fresh_state()
    before = datetime.now(timezone.utc)

    scheduler_service.mark_document_finished(42)

    stamped = scheduler_service.get_scheduler_status()["last_finished_at"]
    assert stamped is not None
    assert datetime.fromisoformat(stamped) >= before.replace(microsecond=0)


def test_the_stamp_outlives_the_run():
    """The run ends after its last document; wiping the stamp then would make
    the stale list look current again."""
    _fresh_state()
    scheduler_service.mark_document_finished(42)
    stamped = scheduler_service.get_scheduler_status()["last_finished_at"]

    scheduler_service._clear_processing()

    assert scheduler_service.get_scheduler_status()["last_finished_at"] == stamped


def test_a_later_document_moves_the_stamp_forward(monkeypatch):
    _fresh_state()
    clock = iter(["2026-09-12T10:00:00+00:00", "2026-09-12T10:05:00+00:00"])
    monkeypatch.setattr(scheduler_service, "_now_iso", lambda: next(clock))

    scheduler_service.mark_document_finished(1)
    scheduler_service.mark_document_finished(2)

    assert scheduler_service.get_scheduler_status()["last_finished_at"] == "2026-09-12T10:05:00+00:00"


def test_a_run_starting_keeps_the_stamp():
    """The scheduler ticks between a finish and the page's return; an empty
    tick used to wipe the stamp and the stale list looked current again."""
    _fresh_state()
    scheduler_service.mark_document_finished(42)
    stamped = scheduler_service.get_scheduler_status()["last_finished_at"]

    started, _ = scheduler_service.try_trigger_processing()
    assert started
    assert scheduler_service.get_scheduler_status()["last_finished_at"] == stamped
    scheduler_service._clear_processing()

    assert scheduler_service.get_scheduler_status()["last_finished_at"] == stamped


def test_a_single_document_run_starting_keeps_the_stamp():
    _fresh_state()
    scheduler_service.mark_document_finished(42)
    stamped = scheduler_service.get_scheduler_status()["last_finished_at"]

    scheduler_service._set_processing(7)

    assert scheduler_service.get_scheduler_status()["last_finished_at"] == stamped
    scheduler_service._clear_processing()


def test_a_state_file_from_before_reports_none():
    """Older state files lack the key; the status must not blow up on them."""
    _fresh_state()
    state = scheduler_service._load_state()
    state.pop("last_finished_at", None)
    scheduler_service._save_state(state)

    assert scheduler_service.get_scheduler_status()["last_finished_at"] is None
