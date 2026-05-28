"""FastAPI entry point for Paperless-AIssist.

The application initializes the database, loads default prompts from the examples
directory, configures logging, seeds environment variables into config, and
manages scheduler lifecycle. All routes require authentication when auth is enabled.
"""

import logging
import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from sqlmodel import select

from .database import run_migrations, get_session
from .models import Config
from .routers import app_info, config as config_router, prompts, documents, stats, scheduler, auth as auth_router
from .auth import require_auth
from .services.log_stream import BroadcastHandler, apply_log_level
from .limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

_broadcast_handler = BroadcastHandler()
_broadcast_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)

def _attach_broadcast_handler():
    """Re-attach broadcast handler after uvicorn replaces logging config."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if _broadcast_handler not in root_logger.handlers:
        root_logger.addHandler(_broadcast_handler)
    for _name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "app.services.processor",
        "app.services.llm_handler",
        "app.services.paperless",
        "app.services.vision",
        "app.services.scheduler",
        "app.routers.config",
        "app.routers.documents",
        "app.routers.scheduler",
    ):
        _logger = logging.getLogger(_name)
        _logger.disabled = False
        _logger.setLevel(logging.INFO)
        # Remove duplicate BroadcastHandler from child loggers;
        # they propagate to root which already has it.
        for h in list(_logger.handlers):
            if isinstance(h, BroadcastHandler):
                _logger.removeHandler(h)


def get_config_value(key: str, default: str = "*") -> str:
    """Retrieve a configuration value from the database.

    Args:
        key: The configuration key to look up.
        default: Default value if key is not found.

    Returns:
        The configuration value, or the default if not found.
    """
    with get_session() as session:
        stmt = select(Config).where(Config.key == key)
        config = session.exec(stmt).first()
        return config.value if config else default


def _seed_env_configs():
    """Seed environment variable values into the Config table on first startup.

    Scans all known config keys and inserts entries for any that have
    an environment variable set but no existing database row. This allows
    all downstream consumers (Paperless client, LLM handler, test
    connection) to find values from .env without individual fallback logic.
    """
    from .routers.config import KNOWN_CONFIG_KEYS, SENSITIVE_KEYS

    with get_session() as session:
        stmt = select(Config)
        existing_keys = {c.key for c in session.exec(stmt).all()}

        for key in sorted(KNOWN_CONFIG_KEYS | SENSITIVE_KEYS):
            if key in existing_keys:
                continue
            env_key = key.upper().replace("-", "_")
            env_val = os.environ.get(env_key)
            if env_val:
                session.add(Config(key=key, value=env_val))

        session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup (DB creation, prompt loading, scheduler auto-start) and
    shutdown (LLM handler and Paperless client cleanup).
    """
    run_migrations()
    _attach_broadcast_handler()

    from .database import get_session
    from .models import Prompt, Config
    from .services.prompt_samples import load_samples, sample_payload
    from sqlmodel import select
    from datetime import datetime, timezone

    default_prompts = load_samples()

    with get_session() as session:
        stmt = select(Config).where(Config.key == "log_level")
        log_cfg = session.exec(stmt).first()
        if log_cfg:
            apply_log_level(log_cfg.value)

    with get_session() as session:
        now = datetime.now(timezone.utc)
        for p in default_prompts.values():
            stmt = select(Prompt).where(Prompt.name == p["name"])
            existing = session.exec(stmt).first()
            if not existing:
                db_prompt = Prompt(
                    **sample_payload(p),
                    sample_key=p["sample_key"],
                    sample_hash=p["sample_hash"],
                    sample_updated_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(db_prompt)

    # Seed env vars into DB on first startup so all consumers find them
    _seed_env_configs()

    from .services.scheduler import (
        clear_processing_state,
        load_scheduler_config,
        start_scheduler,
    )

    clear_processing_state()

    _logger = logging.getLogger(__name__)
    enabled, interval = load_scheduler_config()
    if enabled:
        try:
            start_scheduler(interval)
            _logger.info(f"Scheduler auto-started with {interval} minute interval")
        except Exception as e:
            _logger.error(f"Failed to auto-start scheduler: {e}")

    yield

    from .services.paperless_manager import PaperlessClientManager
    from .services.llm_handler import LLMHandlerManager

    await PaperlessClientManager.close()
    await LLMHandlerManager.close()


run_migrations()

app = FastAPI(
    title="Paperless-AIssist",
    description="AI-powered document processing for Paperless-ngx",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_auth_dep = [Depends(require_auth)]

app.include_router(auth_router.router)
app.include_router(config_router.router, dependencies=_auth_dep)
app.include_router(prompts.router, dependencies=_auth_dep)
app.include_router(documents.router, dependencies=_auth_dep)
app.include_router(stats.router)
app.include_router(scheduler.router, dependencies=_auth_dep)
app.include_router(app_info.router)


@app.get("/api/status")
async def status():
    return {
        "status": "running",
        "service": "Paperless-AIssist",
    }
