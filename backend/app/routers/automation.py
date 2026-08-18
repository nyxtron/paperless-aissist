"""Automation API endpoints for external clients."""

import logging

from fastapi import APIRouter, Depends

from ..auth import require_automation_auth
from ..services.automation import (
    get_automation_status,
    start_automation_processing,
    stop_automation_processing,
)

router = APIRouter(
    prefix="/api/automation",
    tags=["automation"],
    dependencies=[Depends(require_automation_auth)],
)
logger = logging.getLogger(__name__)


@router.get("/status")
# Two of the three endpoints sit under /process/, so that is the path people reach for
# when they need the third. Kept out of the schema: /status stays the documented one,
# this only spares the guess a 404 that our JSON error body makes hard to spot.
@router.get("/process/status", include_in_schema=False)
async def status():
    """Return the current processing state."""
    logger.info("Automation API status requested")
    result = get_automation_status()
    logger.info(
        "Automation API status returned: is_processing=%s automation_running=%s",
        result.get("is_processing"),
        result.get("automation_running"),
    )
    return result


@router.post("/process/start")
async def start_process_all():
    """Start processing all tagged documents in the background."""
    logger.info("Automation API start requested")
    result = await start_automation_processing()
    logger.info("Automation API start result: status=%s", result.get("status"))
    return result


@router.post("/process/stop")
async def stop_process_all():
    """Stop an automation-owned processing run."""
    logger.info("Automation API stop requested")
    result = await stop_automation_processing()
    logger.info("Automation API stop result: status=%s", result.get("status"))
    return result
