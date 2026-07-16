"""APScheduler-based background scheduler for auto-processing Paperless documents.

Supports configurable intervals, concurrent processing limits, and persistent state
across restarts. Exposes start/stop/trigger/update functions and status queries.
"""

import logging
import os
import json
import asyncio
import threading
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from typing import Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CONCURRENT_PROCESSING = 3


async def get_max_concurrent_processing() -> int:
    """Return the configured parallel processing limit (default 3, minimum 1)."""
    from .config_cache import ConfigCache

    try:
        cache = await ConfigCache.get_instance()
        value = int(await cache.get("max_concurrent_processing", ""))
    except (ValueError, TypeError):
        return _DEFAULT_MAX_CONCURRENT_PROCESSING
    except Exception as e:
        logger.warning(f"Could not read max_concurrent_processing: {e}")
        return _DEFAULT_MAX_CONCURRENT_PROCESSING
    return max(1, value)

scheduler: Optional[AsyncIOScheduler] = None
job_id = "auto_process_documents"
lock = threading.RLock()

_lock: Optional[asyncio.Lock] = None


async def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
)
os.makedirs(DATA_DIR, exist_ok=True)
STATE_FILE = os.path.join(DATA_DIR, "scheduler_state.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> dict[str, Any]:
    return {
        "is_processing": False,
        "started_at": None,
        "active_documents": [],
    }


def _normalize_state(state: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _default_state()
    if isinstance(state, dict):
        normalized.update(state)

    active_documents = normalized.get("active_documents")
    if not isinstance(active_documents, list):
        active_documents = []
    normalized["active_documents"] = [
        doc
        for doc in active_documents
        if isinstance(doc, dict) and doc.get("document_id") is not None
    ]

    return normalized


def _running_seconds(started_at: Optional[str]) -> Optional[float]:
    if not started_at:
        return None
    try:
        parsed = datetime.fromisoformat(started_at)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - parsed).total_seconds(), 1)
    except ValueError:
        return None


def _active_document_payload(
    doc_id: int,
    trigger_tags: Optional[list[str]] = None,
    trigger_mode: Optional[str] = None,
    active_step: Optional[str] = None,
    started_at: Optional[str] = None,
) -> dict[str, Any]:
    clean_trigger_tags = [tag for tag in (trigger_tags or []) if tag]
    return {
        "document_id": doc_id,
        "trigger_tags": clean_trigger_tags,
        "trigger_mode": trigger_mode
        or (clean_trigger_tags[0] if clean_trigger_tags else None),
        "active_step": active_step,
        "started_at": started_at or _now_iso(),
    }


def _load_state() -> dict:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return _normalize_state(json.load(f))
    except Exception as e:
        logger.error(f"Failed to load state: {e}")
    return _default_state()


def _save_state(state: dict):
    try:
        tmp_file = f"{STATE_FILE}.tmp"
        with open(tmp_file, "w") as f:
            json.dump(state, f)
        os.replace(tmp_file, STATE_FILE)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")


def _set_processing(
    doc_id: Optional[int] = None,
    trigger_tags: Optional[list[str]] = None,
    trigger_mode: Optional[str] = None,
):
    with lock:
        started_at = _now_iso()
        active_documents = []
        if doc_id is not None:
            active_documents.append(
                _active_document_payload(
                    doc_id,
                    trigger_tags=trigger_tags,
                    trigger_mode=trigger_mode,
                    started_at=started_at,
                )
            )
        state = {
            "is_processing": True,
            "started_at": started_at,
            "active_documents": active_documents,
        }
        _save_state(state)


def _clear_processing():
    """Reset the processing state file (called after each run or on interrupt)."""
    with lock:
        state = _default_state()
        _save_state(state)


def mark_document_started(
    doc_id: int,
    trigger_tags: Optional[list[str]] = None,
    trigger_mode: Optional[str] = None,
    active_step: Optional[str] = None,
):
    """Record a document as actively processing within the current run."""
    with lock:
        state = _load_state()
        if not state.get("started_at"):
            state["started_at"] = _now_iso()
        state["is_processing"] = True

        active_documents = [
            doc
            for doc in state.get("active_documents", [])
            if doc.get("document_id") != doc_id
        ]
        active_documents.append(
            _active_document_payload(
                doc_id,
                trigger_tags=trigger_tags,
                trigger_mode=trigger_mode,
                active_step=active_step,
            )
        )
        state["active_documents"] = active_documents
        _save_state(state)


def update_active_document(
    doc_id: int,
    trigger_tags: Optional[list[str]] = None,
    trigger_mode: Optional[str] = None,
    active_step: Optional[str] = None,
):
    """Update metadata for an active document without resetting its timer."""
    with lock:
        state = _load_state()
        active_documents = state.get("active_documents", [])
        for doc in active_documents:
            if doc.get("document_id") != doc_id:
                continue
            if trigger_tags is not None:
                doc["trigger_tags"] = [tag for tag in trigger_tags if tag]
            if trigger_mode is not None:
                doc["trigger_mode"] = trigger_mode
            if active_step is not None:
                doc["active_step"] = active_step
            break
        state["active_documents"] = active_documents
        _save_state(state)


def mark_document_finished(doc_id: int):
    """Remove a document from the active processing list."""
    with lock:
        state = _load_state()
        active_documents = [
            doc
            for doc in state.get("active_documents", [])
            if doc.get("document_id") != doc_id
        ]
        state["active_documents"] = active_documents
        _save_state(state)


def get_processing_state() -> dict[str, Any]:
    """Return normalized processing state with computed runtime fields."""
    with lock:
        state = _load_state()

    active_documents = []
    for doc in state.get("active_documents", []):
        active_doc = dict(doc)
        active_doc["running_seconds"] = _running_seconds(active_doc.get("started_at"))
        active_documents.append(active_doc)

    state["active_documents"] = active_documents
    state["current_document_ids"] = [
        doc["document_id"] for doc in active_documents
    ]
    state["running_seconds"] = _running_seconds(state.get("started_at"))
    return state


def is_currently_processing() -> tuple[bool, Optional[int]]:
    state = get_processing_state()
    current_document_ids = state.get("current_document_ids", [])
    first_doc_id = current_document_ids[0] if current_document_ids else None
    return state.get("is_processing", False), first_doc_id


def load_scheduler_config() -> tuple[bool, int]:
    """Load scheduler config from database. Returns (enabled, interval_minutes)."""
    try:
        from ..database import get_session
        from ..models import Config
        from sqlmodel import select

        with get_session() as session:
            stmt = select(Config).where(Config.key == "scheduler_enabled")
            enabled_config = session.exec(stmt).first()
            enabled = enabled_config.value == "true" if enabled_config else False

            stmt = select(Config).where(Config.key == "scheduler_interval")
            interval_config = session.exec(stmt).first()
            interval = int(interval_config.value) if interval_config else 5

            return enabled, interval
    except Exception as e:
        logger.error(f"Failed to load scheduler config: {e}")
        return False, 5


def save_scheduler_config(enabled: bool, interval_minutes: int):
    """Save scheduler config to database."""
    try:
        from ..database import get_session
        from ..models import Config
        from sqlmodel import select

        with get_session() as session:
            stmt = select(Config).where(Config.key == "scheduler_enabled")
            config = session.exec(stmt).first()
            if config:
                config.value = "true" if enabled else "false"
            else:
                session.add(
                    Config(
                        key="scheduler_enabled", value="true" if enabled else "false"
                    )
                )

            stmt = select(Config).where(Config.key == "scheduler_interval")
            config = session.exec(stmt).first()
            if config:
                config.value = str(interval_minutes)
            else:
                session.add(
                    Config(key="scheduler_interval", value=str(interval_minutes))
                )
    except Exception as e:
        logger.error(f"Failed to save scheduler config: {e}")


def create_scheduler() -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    return scheduler


async def process_documents_task():
    with lock:
        is_running, _ = is_currently_processing()
        if is_running:
            logger.info("Skipping scheduled run - already processing")
            return

    _set_processing()

    try:
        result = await process_tagged_documents()

        if result.get("processed", 0) > 0:
            logger.info(f"Auto-processed {result.get('processed')} documents")
    except Exception as e:
        logger.error(f"Auto-processing failed: {e}")

    try:
        modular_result = await process_modular_tagged_documents()
        if modular_result.get("processed", 0) > 0:
            logger.info(
                f"Auto-processed {modular_result.get('processed')} documents (modular pipeline)"
            )
    except Exception as e:
        logger.error(f"Modular auto-processing failed: {e}")
    finally:
        with lock:
            _clear_processing()


def start_scheduler(interval_minutes: int = 5):
    """Start (or restart) the APScheduler with the given interval in minutes.

    Args:
        interval_minutes: How often to run the auto-processing job.
    """
    global scheduler

    if scheduler is None:
        scheduler = create_scheduler()

    if scheduler.running:
        scheduler.shutdown()

    scheduler.add_job(
        process_documents_task,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=job_id,
        replace_existing=True,
    )
    scheduler.start()
    save_scheduler_config(True, interval_minutes)
    logger.info(f"Scheduler started with {interval_minutes} minute interval")


def stop_scheduler():
    """Stop the scheduler and persist disabled state to the database."""
    global scheduler

    if scheduler and scheduler.running:
        scheduler.shutdown()
    save_scheduler_config(False, 5)
    logger.info("Scheduler stopped")


def get_scheduler_status() -> dict:
    """Return current scheduler status including running state and next run time."""
    global scheduler

    processing_state = get_processing_state()

    if scheduler is None or not scheduler.running:
        return {
            "running": False,
            "interval_minutes": None,
            "next_run": None,
            "is_processing": processing_state["is_processing"],
            "current_document_ids": processing_state["current_document_ids"],
            "active_documents": processing_state["active_documents"],
            "started_at": processing_state["started_at"],
            "running_seconds": processing_state["running_seconds"],
        }

    job = scheduler.get_job(job_id)
    if job and job.next_run_time:
        return {
            "running": True,
            "interval_minutes": job.trigger.interval.total_seconds() / 60,
            "next_run": job.next_run_time.isoformat(),
            "is_processing": processing_state["is_processing"],
            "current_document_ids": processing_state["current_document_ids"],
            "active_documents": processing_state["active_documents"],
            "started_at": processing_state["started_at"],
            "running_seconds": processing_state["running_seconds"],
        }

    return {
        "running": False,
        "interval_minutes": None,
        "next_run": None,
        "is_processing": processing_state["is_processing"],
        "current_document_ids": processing_state["current_document_ids"],
        "active_documents": processing_state["active_documents"],
        "started_at": processing_state["started_at"],
        "running_seconds": processing_state["running_seconds"],
    }


def update_scheduler_interval(interval_minutes: int):
    """Update the polling interval of a running scheduler."""
    global scheduler

    if scheduler and scheduler.running:
        job = scheduler.get_job(job_id)
        if job:
            scheduler.remove_job(job_id)

        scheduler.add_job(
            process_documents_task,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            replace_existing=True,
        )
        save_scheduler_config(True, interval_minutes)
        logger.info(f"Scheduler interval updated to {interval_minutes} minutes")


def try_trigger_processing() -> tuple[bool, str]:
    """Try to mark processing as started; rejects if already in progress.

    Returns:
        (True, message) on success, (False, reason) if already running.
    """
    with lock:
        is_running, doc_id = is_currently_processing()
        if is_running:
            if doc_id is not None:
                return False, f"Already processing document #{doc_id}"
            return False, "Already processing documents"
        _set_processing()

    return True, "Processing started"


def clear_processing_state():
    """Clear processing state (e.g., on startup if was interrupted)."""
    is_running, doc_id = is_currently_processing()
    if is_running:
        logger.warning(
            f"Clearing stale processing state (was processing doc #{doc_id})"
        )
        _clear_processing()


async def process_tagged_documents() -> dict:
    """Process all documents tagged with the legacy process_tag.

    Returns:
        Dict with "processed" count and "results" list.
    """
    from ..services.paperless_manager import PaperlessClientManager
    from ..services.processor import DocumentProcessor

    try:
        paperless = await PaperlessClientManager.get_client()
        processor = DocumentProcessor(paperless)
        result = await processor.process_tagged_documents()

        if result.get("processed", 0) > 0:
            logger.info(f"Processed {result.get('processed')} documents")

        return result
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise


async def process_modular_tagged_documents() -> dict:
    """Process all documents tagged with any modular trigger tag.

    Returns:
        Dict with "processed" count and "results" list.
    """
    from ..services.paperless_manager import PaperlessClientManager
    from ..services.processor import DocumentProcessor

    paperless = await PaperlessClientManager.get_client()
    paperless.reset_metrics()
    started = asyncio.get_running_loop().time()
    processor = DocumentProcessor(paperless)
    tag_map = await processor._get_modular_tag_map()
    process_tag_name = await processor._get_config("process_tag")
    trigger_tag_names = [
        tag_name for tag_name in tag_map.values() if tag_name != process_tag_name
    ]

    all_tags = await paperless.get_tags()
    tag_name_to_id = {t["name"]: t["id"] for t in all_tags}

    trigger_tag_ids = {
        tag_name_to_id[tag_name]
        for tag_name in trigger_tag_names
        if tag_name in tag_name_to_id
    }
    if not trigger_tag_ids:
        return {"success": True, "processed": 0, "results": []}

    docs = await paperless.list_documents(tags_any=sorted(trigger_tag_ids))
    doc_ids = {doc["id"] for doc in docs}

    logger.debug(
        "Scheduler modular scan: %d docs matched across %d trigger tags",
        len(doc_ids),
        len(trigger_tag_ids),
    )

    if not doc_ids:
        return {"success": True, "processed": 0, "results": []}

    # Keep compatibility: preserve existing per-doc processing behavior.
    for tag_name in trigger_tag_names:
        if tag_name not in tag_name_to_id:
            logger.debug("Scheduler modular tag %r not found in Paperless", tag_name)

    async def process_one(doc_id: int):
        return await processor.process_document(doc_id)

    max_parallel = await get_max_concurrent_processing()
    logger.info(
        "Processing %d documents (up to %d in parallel)", len(doc_ids), max_parallel
    )
    sem = asyncio.Semaphore(max_parallel)

    async def _limited_process(doc_id: int):
        async with sem:
            return await process_one(doc_id)

    results = await asyncio.gather(
        *[_limited_process(d) for d in doc_ids], return_exceptions=True
    )

    successful_results = [
        r
        for r in results
        if not isinstance(r, Exception) and r.get("success") is True
    ]
    failed_results = [
        r
        for r in results
        if isinstance(r, Exception) or r.get("success") is not True
    ]
    processed = len(successful_results)
    errors = [
        str(r) if isinstance(r, Exception) else r.get("error", "Processing failed")
        for r in failed_results
    ]
    if errors:
        logger.warning(f"Modular processing errors: {errors}")
    metrics = paperless.get_metrics()
    logger.debug(
        "Scheduler modular run: processed=%d/%d, requests=%d (paged=%d), duration=%.2fs",
        processed,
        len(doc_ids),
        metrics["requests"],
        metrics["paged_requests"],
        asyncio.get_running_loop().time() - started,
    )
    return {
        "success": len(failed_results) == 0,
        "processed": processed,
        "failed": len(failed_results),
        "results": [r for r in results if not isinstance(r, Exception)],
    }
