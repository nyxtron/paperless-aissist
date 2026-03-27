import logging
import os
import json
import asyncio
import threading
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

scheduler: Optional[AsyncIOScheduler] = None
job_id = "auto_process_documents"
lock = threading.Lock()

DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
)
os.makedirs(DATA_DIR, exist_ok=True)
STATE_FILE = os.path.join(DATA_DIR, "scheduler_state.json")


def _load_state() -> dict:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load state: {e}")
    return {"is_processing": False, "current_doc_id": None, "started_at": None}


def _save_state(state: dict):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")


def _set_processing(doc_id: Optional[int] = None):
    state = _load_state()
    state["is_processing"] = True
    state["current_doc_id"] = doc_id
    state["started_at"] = datetime.utcnow().isoformat()
    _save_state(state)


def _clear_processing():
    state = _load_state()
    state["is_processing"] = False
    state["current_doc_id"] = None
    state["started_at"] = None
    _save_state(state)


def is_currently_processing() -> tuple[bool, Optional[int]]:
    state = _load_state()
    return state.get("is_processing", False), state.get("current_doc_id")


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
    global scheduler

    if scheduler and scheduler.running:
        scheduler.shutdown()
    save_scheduler_config(False, 5)
    logger.info("Scheduler stopped")


def get_scheduler_status() -> dict:
    global scheduler

    is_processing, current_doc_id = is_currently_processing()

    if scheduler is None or not scheduler.running:
        return {
            "running": False,
            "interval_minutes": None,
            "next_run": None,
            "is_processing": is_processing,
            "current_doc_id": current_doc_id,
        }

    job = scheduler.get_job(job_id)
    if job and job.next_run_time:
        return {
            "running": True,
            "interval_minutes": job.trigger.interval.total_seconds() / 60,
            "next_run": job.next_run_time.isoformat(),
            "is_processing": is_processing,
            "current_doc_id": current_doc_id,
        }

    return {
        "running": False,
        "interval_minutes": None,
        "next_run": None,
        "is_processing": is_processing,
        "current_doc_id": current_doc_id,
    }


def update_scheduler_interval(interval_minutes: int):
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
    """Try to start processing. Returns (success, message)."""
    with lock:
        is_running, doc_id = is_currently_processing()
        if is_running:
            return False, f"Already processing document #{doc_id}"
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
    """Process all tagged documents. Handles state management. Returns result dict."""
    from ..services.paperless import PaperlessClient
    from ..services.processor import DocumentProcessor

    try:
        paperless = await PaperlessClient.from_config()
        processor = DocumentProcessor(paperless)
        result = await processor.process_tagged_documents()
        await paperless.close()

        if result.get("processed", 0) > 0:
            logger.info(f"Processed {result.get('processed')} documents")

        return result
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise


async def process_modular_tagged_documents() -> dict:
    """Process all modular-tagged documents. Returns result dict."""
    from ..services.paperless import PaperlessClient
    from ..services.processor import DocumentProcessor

    paperless = await PaperlessClient.from_config()
    processor = DocumentProcessor(paperless)
    tag_map = await processor._get_modular_tag_map()
    trigger_tag_names = list(tag_map.values())

    all_tags = await paperless.get_tags()
    tag_name_to_id = {t["name"]: t["id"] for t in all_tags}

    doc_ids: set[int] = set()
    for tag_name in trigger_tag_names:
        tag_id = tag_name_to_id.get(tag_name)
        if not tag_id:
            continue
        try:
            docs = await paperless.list_documents(tags=[tag_id])
            for doc in docs:
                doc_ids.add(doc["id"])
        except Exception as e:
            logger.warning(f"Failed to list docs for modular tag {tag_name!r}: {e}")

    results = []
    for doc_id in doc_ids:
        result = await processor.process_document(doc_id)
        results.append(result)

    await paperless.close()
    return {
        "success": True,
        "processed": len(results),
        "results": results,
    }
