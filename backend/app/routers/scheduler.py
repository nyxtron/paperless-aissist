from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from ..services.scheduler import (
    start_scheduler,
    stop_scheduler,
    get_scheduler_status,
    update_scheduler_interval,
    try_trigger_processing,
    clear_processing_state,
    process_tagged_documents,
    _clear_processing,
)

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


class SchedulerUpdate(BaseModel):
    enabled: bool
    interval: int


@router.get("")
async def get_scheduler():
    return get_scheduler_status()


@router.post("/start")
async def start(interval_minutes: int = 5):
    start_scheduler(interval_minutes)
    return {
        "success": True,
        "message": f"Scheduler started with {interval_minutes} minute interval",
    }


@router.post("/stop")
async def stop():
    stop_scheduler()
    return {"success": True, "message": "Scheduler stopped"}


@router.put("")
async def update_scheduler(data: SchedulerUpdate = Body(...)):
    update_scheduler_interval(data.interval)
    if data.enabled:
        start_scheduler(data.interval)
    else:
        stop_scheduler()
    return {
        "success": True,
        "message": f"Scheduler {'started' if data.enabled else 'stopped'} with {data.interval} minute interval",
    }


@router.post("/trigger-now")
async def trigger_now():
    success, message = try_trigger_processing()
    if not success:
        raise HTTPException(status_code=409, detail=message)

    try:
        result = await process_tagged_documents()
        return {"success": True, "processed": result.get("processed", 0)}
    except Exception as e:
        _clear_processing()
        return {"success": False, "error": str(e)}
    finally:
        _clear_processing()


@router.post("/clear-state")
async def clear_state():
    """Clear processing state if stuck (e.g., after app restart)."""
    clear_processing_state()
    return {"success": True, "message": "Processing state cleared"}
