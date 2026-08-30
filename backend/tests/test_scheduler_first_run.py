"""Pressing Start checks once right away (issue #43).

The job used to be added with the interval trigger alone, so APScheduler put the
first run a full interval into the future. On a five minute interval that reads
as nothing having happened.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.services import scheduler as scheduler_service


def _start(interval_minutes: int = 5):
    with patch.object(scheduler_service, "save_scheduler_config"):
        scheduler_service.start_scheduler(interval_minutes)
    return scheduler_service.scheduler.get_job(scheduler_service.job_id)


@pytest.mark.asyncio
async def test_first_run_is_due_immediately():
    try:
        job = _start()
        assert job is not None
        assert job.next_run_time <= datetime.now(timezone.utc) + timedelta(seconds=5)
    finally:
        scheduler_service.stop_scheduler()


@pytest.mark.asyncio
async def test_the_interval_still_governs_later_runs():
    try:
        job = _start(interval_minutes=7)
        assert job.trigger.interval == timedelta(minutes=7)
    finally:
        scheduler_service.stop_scheduler()
