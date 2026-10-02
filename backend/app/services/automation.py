"""External automation process control.

Provides background start/stop/status helpers for API clients that trigger the
same "process all" workflow as the UI without blocking the HTTP request.
"""

import asyncio
import json
import logging
import os
from typing import Optional

from .scheduler import (
    DATA_DIR,
    REVIEW_STOP_KIND,
    _clear_processing,
    get_processing_state,
    process_modular_tagged_documents,
    process_tagged_documents,
    try_trigger_processing,
)

logger = logging.getLogger(__name__)

_automation_task: Optional[asyncio.Task] = None
_last_result: Optional[dict] = None
LAST_RESULT_FILE = os.path.join(DATA_DIR, "automation_last_result.json")


def _is_automation_task_running() -> bool:
    return _automation_task is not None and not _automation_task.done()


def _compact_result_for_status(result: dict) -> dict:
    """Remove heavy fields from results returned by the Automation API status."""
    compact = dict(result)
    compact.pop("proposed_changes", None)
    return compact


def _compact_results_for_status(results: list) -> list[dict]:
    return [
        _compact_result_for_status(result)
        for result in results
        if isinstance(result, dict)
    ]


def _load_last_result() -> Optional[dict]:
    try:
        if not os.path.exists(LAST_RESULT_FILE):
            return None
        with open(LAST_RESULT_FILE, "r", encoding="utf-8") as file:
            result = json.load(file)
        return result if isinstance(result, dict) else None
    except Exception as exc:
        logger.error("Failed to load Automation API last result: %s", exc)
        return None


def _save_last_result(result: dict) -> None:
    try:
        os.makedirs(os.path.dirname(LAST_RESULT_FILE), exist_ok=True)
        tmp_file = f"{LAST_RESULT_FILE}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as file:
            json.dump(result, file)
        os.replace(tmp_file, LAST_RESULT_FILE)
    except Exception as exc:
        logger.error("Failed to save Automation API last result: %s", exc)


def _set_last_result(result: dict) -> None:
    global _last_result
    _last_result = result
    _save_last_result(result)


def _get_last_result() -> Optional[dict]:
    global _last_result
    if _last_result is None:
        _last_result = _load_last_result()
    return _last_result


async def _run_process_all() -> None:
    try:
        logger.info("Automation API process-all run started")
        legacy = await process_tagged_documents()
        stop = legacy.get("stop") or {}
        if stop.get("kind") == REVIEW_STOP_KIND:
            logger.warning("Modular pass skipped: %s", stop.get("reason"))
            modular = {}
        else:
            modular = await process_modular_tagged_documents()
        failed = legacy.get("failed", 0) + modular.get("failed", 0)
        results = legacy.get("results", []) + modular.get("results", [])
        last_result = {
            "success": failed == 0 and not stop,
            "status": "completed",
            "processed": legacy.get("processed", 0) + modular.get("processed", 0),
            "failed": failed,
            "results": _compact_results_for_status(results),
        }
        if stop:
            last_result["stop"] = stop
        _set_last_result(last_result)
        logger.info(
            "Automation API process-all run completed: processed=%s failed=%s",
            last_result["processed"],
            last_result["failed"],
        )
    except asyncio.CancelledError:
        logger.info("Automation API process-all run cancelled")
        _set_last_result(
            {
                "success": False,
                "status": "cancelled",
                "error": "Processing cancelled",
            }
        )
    except Exception as exc:
        logger.error("Automation API process-all run failed: %s", exc)
        _set_last_result(
            {
                "success": False,
                "status": "failed",
                "error": str(exc),
            }
        )
    finally:
        _clear_processing()


async def start_automation_processing() -> dict:
    """Start process-all in the background, or report the existing run."""
    global _automation_task

    if _is_automation_task_running():
        return {
            "success": True,
            "status": "already_running",
            "message": "Automation processing already running",
        }

    success, message = try_trigger_processing()
    if not success:
        return {"success": True, "status": "already_running", "message": message}

    _automation_task = asyncio.create_task(_run_process_all())
    return {"success": True, "status": "started", "message": "Processing started"}


async def stop_automation_processing() -> dict:
    """Request cancellation of the current automation-owned run."""
    if not _is_automation_task_running():
        return {
            "success": True,
            "status": "not_running",
            "message": "No automation processing run is active",
        }

    assert _automation_task is not None
    _automation_task.cancel()
    return {
        "success": True,
        "status": "stopping",
        "message": "Automation processing stop requested",
    }


def get_automation_status() -> dict:
    """Return current process state and the last automation result."""
    processing_state = get_processing_state()
    return {
        "success": True,
        "is_processing": processing_state["is_processing"],
        "current_document_ids": processing_state["current_document_ids"],
        "active_documents": processing_state["active_documents"],
        "started_at": processing_state["started_at"],
        "running_seconds": processing_state["running_seconds"],
        "automation_running": _is_automation_task_running(),
        "last_result": _get_last_result(),
    }
