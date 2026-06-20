"""FastAPI entry point for Paperless-AIssist.

The application initializes the database, loads default prompts from the examples
directory, configures logging, and manages scheduler lifecycle. All routes require
authentication when auth is enabled.
"""

import logging
import os

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from sqlmodel import select

from .database import run_migrations, get_session
from .models import Config
from .constants import APP_VERSION
from .routers import (
    app_info,
    automation,
    config,
    prompts,
    documents,
    stats,
    scheduler,
    auth as auth_router,
)
from .auth import require_auth
from .services.log_stream import BroadcastHandler, apply_log_level
from .limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from .mcp.server import build_mcp_app

_broadcast_handler = BroadcastHandler()
_broadcast_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)

# Build the MCP ASGI sub-app once at import time so the lifespan context manager
# and the app.mount() call both reference the same Starlette app object.
# The gate middleware inside the sub-app checks mcp_enabled live per request.
_mcp_app = build_mcp_app()


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
        "app.services.automation",
        "app.routers.config",
        "app.routers.documents",
        "app.routers.scheduler",
        "app.routers.automation",
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

    # Enter the MCP app's lifespan so its StreamableHTTPSessionManager task group
    # starts and stops alongside the FastAPI app. FastAPI does not run the lifespan
    # of mounted sub-apps, so we must do this explicitly.
    async with _mcp_app.lifespan(_mcp_app):
        yield

    from .services.paperless_manager import PaperlessClientManager
    from .services.llm_handler import LLMHandlerManager

    await PaperlessClientManager.close()
    await LLMHandlerManager.close()


run_migrations()

app = FastAPI(
    title="Paperless-AIssist",
    description="AI-powered document processing for Paperless-ngx",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Self-hosted app: permissive CORS by default — the web UI is same-origin
# (nginx proxies /api) and the Automation API is server-to-server, so this only
# matters for cross-origin browser callers. Set CORS_ALLOW_ORIGINS to a
# comma-separated list to restrict; leave unset (or "*") to allow all.
_cors_origins_raw = os.environ.get("CORS_ALLOW_ORIGINS", "*").strip()
_cors_origins = (
    ["*"]
    if _cors_origins_raw in ("", "*")
    else [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_auth_dep = [Depends(require_auth)]

app.include_router(auth_router.router)
app.include_router(config.router, dependencies=_auth_dep)
app.include_router(prompts.router, dependencies=_auth_dep)
app.include_router(documents.router, dependencies=_auth_dep)
app.include_router(stats.router)
app.include_router(scheduler.router, dependencies=_auth_dep)
app.include_router(automation.router)
app.include_router(app_info.router)

app.mount("/mcp", _mcp_app)


@app.get("/api/status")
async def status():
    return {
        "status": "running",
        "service": "Paperless-AIssist",
    }
