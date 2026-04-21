"""FastAPI entry point for Paperless-AIssist.

The application initializes the database, loads default prompts from the examples
directory, configures logging, and manages scheduler lifecycle. All routes require
authentication when auth is enabled.
"""

import json
import logging
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from sqlmodel import select

from .database import run_migrations, get_session
from .models import Config
from .routers import config, prompts, documents, stats, scheduler, auth as auth_router
from .auth import require_auth
from .services.log_stream import BroadcastHandler, apply_log_level
from .limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

_broadcast_handler = BroadcastHandler()
_broadcast_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
logging.basicConfig(
    level=logging.INFO, handlers=[logging.StreamHandler(), _broadcast_handler]
)
for _name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_name).addHandler(_broadcast_handler)


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

    from .database import get_session
    from .models import Prompt, Config
    from sqlmodel import select
    from datetime import datetime, timezone

    examples_dir = Path(__file__).parent.parent.parent / "examples" / "prompts"
    default_prompts = []
    if examples_dir.exists():
        for json_file in sorted(examples_dir.glob("*.json")):
            with open(json_file) as f:
                default_prompts.append(json.load(f))

    with get_session() as session:
        stmt = select(Config).where(Config.key == "log_level")
        log_cfg = session.exec(stmt).first()
        if log_cfg:
            apply_log_level(log_cfg.value)

    with get_session() as session:
        for p in default_prompts:
            stmt = select(Prompt).where(Prompt.name == p["name"])
            existing = session.exec(stmt).first()
            if not existing:
                db_prompt = Prompt(
                    **p,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
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
app.include_router(config.router, dependencies=_auth_dep)
app.include_router(prompts.router, dependencies=_auth_dep)
app.include_router(documents.router, dependencies=_auth_dep)
app.include_router(stats.router, dependencies=_auth_dep)
app.include_router(scheduler.router, dependencies=_auth_dep)


@app.get("/api/status")
async def status():
    return {
        "status": "running",
        "service": "Paperless-AIssist",
    }
