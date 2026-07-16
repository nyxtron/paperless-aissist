"""Prompt template CRUD endpoints with type filtering and sample loading."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..database import get_async_session
from ..models import Prompt
from ..services.prompt_samples import (
    SAMPLE_FIELDS,
    find_sample_for_prompt,
    load_samples,
    normalize_prompt_value,
    sample_payload,
    sample_status,
)

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


class PromptCreate(BaseModel):
    name: str
    prompt_type: str
    document_type_filter: Optional[str] = None
    system_prompt: str
    user_template: str
    is_active: bool = True


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    prompt_type: Optional[str] = None
    document_type_filter: Optional[str] = None
    system_prompt: Optional[str] = None
    user_template: Optional[str] = None
    is_active: Optional[bool] = None


def _serialize_prompt(prompt: Prompt, samples: dict[str, dict] | None = None) -> dict:
    samples = samples or load_samples()
    sample = find_sample_for_prompt(prompt, samples)
    return {
        "id": prompt.id,
        "name": prompt.name,
        "prompt_type": prompt.prompt_type,
        "document_type_filter": prompt.document_type_filter,
        "system_prompt": prompt.system_prompt,
        "user_template": prompt.user_template,
        "is_active": prompt.is_active,
        "created_at": prompt.created_at.isoformat(),
        "updated_at": prompt.updated_at.isoformat(),
        "sample_key": sample["sample_key"] if sample else prompt.sample_key,
        "sample_hash": prompt.sample_hash,
        "sample_status": sample_status(prompt, sample),
    }


def _serialize_sample(sample: dict) -> dict:
    return {
        "name": sample["name"],
        "prompt_type": sample["prompt_type"],
        "document_type_filter": sample.get("document_type_filter"),
        "system_prompt": sample["system_prompt"],
        "user_template": sample["user_template"],
        "is_active": sample["is_active"],
        "sample_key": sample["sample_key"],
        "sample_hash": sample["sample_hash"],
    }


@router.get("")
async def get_prompts():
    """Return all prompt templates."""
    samples = load_samples()
    async with get_async_session() as session:
        stmt = select(Prompt)
        prompts = await session.exec(stmt)
        prompts = prompts.all()
        return [_serialize_prompt(p, samples) for p in prompts]


@router.get("/templates")
async def get_prompt_templates():
    return {
        "variables": [
            {"name": "{content}", "description": "The document text content"},
            {
                "name": "{correspondents_list}",
                "description": "List of available correspondents",
            },
            {"name": "{tags_list}", "description": "List of available tags"},
            {
                "name": "{document_types_list}",
                "description": "List of available document types",
            },
            {
                "name": "{custom_fields_list}",
                "description": "List of available custom fields",
            },
            {
                "name": "{document_custom_fields_list}",
                "description": "Custom fields already assigned to the document",
            },
            {"name": "{title}", "description": "Original document title"},
            {"name": "{created_date}", "description": "Current document date"},
            {"name": "{current_date}", "description": "Current date"},
        ],
        "types": [
            {"value": "correspondent", "description": "Correspondent detection"},
            {"value": "document_type", "description": "Document type detection"},
            {"value": "tag", "description": "Tag detection"},
            {
                "value": "ocr_fix",
                "description": "OCR post-processing (fix recognition errors)",
            },
            {"value": "date", "description": "Document date detection"},
            {
                "value": "classify",
                "description": "Document classification (legacy combined)",
            },
            {"value": "extract", "description": "Custom fields extraction"},
            {
                "value": "type_specific",
                "description": "Type-specific extraction (runs after classify)",
            },
            {"value": "title", "description": "Title generation"},
            {
                "value": "vision_ocr",
                "description": "Vision OCR (prompt sent to vision model for text extraction)",
            },
        ],
    }


@router.get("/{prompt_id}")
async def get_prompt(prompt_id: int):
    """Return a single prompt template by ID."""
    samples = load_samples()
    async with get_async_session() as session:
        stmt = select(Prompt).where(Prompt.id == prompt_id)
        prompt = await session.exec(stmt)
        prompt = prompt.first()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return _serialize_prompt(prompt, samples)


@router.get("/{prompt_id}/sample")
async def get_prompt_sample(prompt_id: int):
    """Return the bundled sample for a prompt without saving it."""
    samples = load_samples()
    async with get_async_session() as session:
        prompt = (await session.exec(select(Prompt).where(Prompt.id == prompt_id))).first()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        sample = find_sample_for_prompt(prompt, samples)
        if not sample:
            raise HTTPException(status_code=404, detail="No bundled sample found for prompt")
        return _serialize_sample(sample)


@router.post("")
async def create_prompt(prompt: PromptCreate):
    """Create a new prompt template."""
    async with get_async_session() as session:
        db_prompt = Prompt(
            name=prompt.name,
            prompt_type=prompt.prompt_type,
            document_type_filter=normalize_prompt_value(
                "document_type_filter",
                prompt.document_type_filter,
            ),
            system_prompt=prompt.system_prompt,
            user_template=prompt.user_template,
            is_active=prompt.is_active,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(db_prompt)
        return {
            "id": db_prompt.id,
            "name": db_prompt.name,
            "message": "Prompt created successfully",
        }


@router.put("/{prompt_id}")
async def update_prompt(prompt_id: int, prompt: PromptUpdate):
    """Update an existing prompt template."""
    samples = load_samples()
    async with get_async_session() as session:
        stmt = select(Prompt).where(Prompt.id == prompt_id)
        db_prompt = await session.exec(stmt)
        db_prompt = db_prompt.first()
        if not db_prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")

        if prompt.name is not None:
            db_prompt.name = prompt.name
        if prompt.prompt_type is not None:
            db_prompt.prompt_type = prompt.prompt_type
        if prompt.document_type_filter is not None:
            db_prompt.document_type_filter = normalize_prompt_value(
                "document_type_filter",
                prompt.document_type_filter,
            )
        if prompt.system_prompt is not None:
            db_prompt.system_prompt = prompt.system_prompt
        if prompt.user_template is not None:
            db_prompt.user_template = prompt.user_template
        if prompt.is_active is not None:
            db_prompt.is_active = prompt.is_active

        sample = find_sample_for_prompt(db_prompt, samples)
        if sample and sample_status(db_prompt, sample) == "sample_current":
            db_prompt.sample_key = sample["sample_key"]
            db_prompt.sample_hash = sample["sample_hash"]
            db_prompt.sample_updated_at = datetime.now(timezone.utc)

        db_prompt.updated_at = datetime.now(timezone.utc)

        return {
            "id": db_prompt.id,
            "name": db_prompt.name,
            "message": "Prompt updated successfully",
        }


@router.post("/load-samples")
async def load_sample_prompts():
    created, updated, skipped = 0, 0, 0
    samples = load_samples()
    now = datetime.now(timezone.utc)
    async with get_async_session() as session:
        for sample in samples.values():
            stmt = select(Prompt).where(Prompt.name == sample["name"])
            existing = await session.exec(stmt)
            existing = existing.first()
            if existing:
                status = sample_status(existing, sample)
                if status == "sample_update_available":
                    for field in SAMPLE_FIELDS:
                        setattr(existing, field, sample[field])
                    existing.sample_key = sample["sample_key"]
                    existing.sample_hash = sample["sample_hash"]
                    existing.sample_updated_at = now
                    existing.updated_at = now
                    updated += 1
                else:
                    if existing.sample_key is None and status == "sample_current":
                        existing.sample_key = sample["sample_key"]
                        existing.sample_hash = sample["sample_hash"]
                        existing.sample_updated_at = now
                    skipped += 1
            else:
                session.add(
                    Prompt(
                        **sample_payload(sample),
                        sample_key=sample["sample_key"],
                        sample_hash=sample["sample_hash"],
                        sample_updated_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
                created += 1

    return {"created": created, "updated": updated, "skipped": skipped}


@router.post("/{prompt_id}/load-sample")
async def load_prompt_sample(prompt_id: int):
    samples = load_samples()
    now = datetime.now(timezone.utc)
    async with get_async_session() as session:
        prompt = (await session.exec(select(Prompt).where(Prompt.id == prompt_id))).first()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        sample = find_sample_for_prompt(prompt, samples)
        if not sample:
            raise HTTPException(status_code=404, detail="No bundled sample found for prompt")

        for field in SAMPLE_FIELDS:
            setattr(prompt, field, sample[field])
        prompt.sample_key = sample["sample_key"]
        prompt.sample_hash = sample["sample_hash"]
        prompt.sample_updated_at = now
        prompt.updated_at = now

        return _serialize_prompt(prompt, samples)


@router.delete("/{prompt_id}")
async def delete_prompt(prompt_id: int):
    """Delete a prompt template by ID."""
    async with get_async_session() as session:
        stmt = select(Prompt).where(Prompt.id == prompt_id)
        prompt = await session.exec(stmt)
        prompt = prompt.first()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        await session.delete(prompt)
        return {"message": "Prompt deleted successfully"}
