import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .database import create_db_and_tables
from .routers import config, prompts, documents, stats, scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()

    from .database import get_session
    from .models import Prompt
    from sqlmodel import select
    from datetime import datetime

    examples_dir = Path(__file__).parent.parent.parent / "examples" / "prompts"
    default_prompts = []
    if examples_dir.exists():
        for json_file in sorted(examples_dir.glob("*.json")):
            with open(json_file) as f:
                default_prompts.append(json.load(f))
    
    with get_session() as session:
        for p in default_prompts:
            stmt = select(Prompt).where(Prompt.name == p["name"])
            existing = session.exec(stmt).first()
            if not existing:
                db_prompt = Prompt(**p, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
                session.add(db_prompt)
    
    from .services.scheduler import clear_processing_state, load_scheduler_config, start_scheduler
    clear_processing_state()
    
    enabled, interval = load_scheduler_config()
    if enabled:
        try:
            start_scheduler(interval)
            print(f"Scheduler auto-started with {interval} minute interval")
        except Exception as e:
            print(f"Failed to auto-start scheduler: {e}")
    
    yield


app = FastAPI(
    title="Paperless-AIssist",
    description="AI-powered document processing for Paperless-ngx",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config.router)
app.include_router(prompts.router)
app.include_router(documents.router)
app.include_router(stats.router)
app.include_router(scheduler.router)


@app.get("/api/status")
async def status():
    return {
        "status": "running",
        "service": "Paperless-AIssist",
    }
