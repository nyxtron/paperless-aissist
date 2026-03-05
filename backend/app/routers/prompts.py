from fastapi import APIRouter, HTTPException
from sqlmodel import select
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from ..database import get_session
from ..models import Prompt

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


@router.get("")
async def get_prompts():
    with get_session() as session:
        stmt = select(Prompt)
        prompts = session.exec(stmt).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "prompt_type": p.prompt_type,
                "document_type_filter": p.document_type_filter,
                "system_prompt": p.system_prompt,
                "user_template": p.user_template,
                "is_active": p.is_active,
                "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
            }
            for p in prompts
        ]


@router.get("/templates")
async def get_prompt_templates():
    return {
        "variables": [
            {"name": "{content}", "description": "The document text content"},
            {"name": "{correspondents_list}", "description": "List of available correspondents"},
            {"name": "{tags_list}", "description": "List of available tags"},
            {"name": "{document_types_list}", "description": "List of available document types"},
            {"name": "{custom_fields_list}", "description": "List of available custom fields"},
            {"name": "{title}", "description": "Original document title"},
        ],
        "types": [
            {"value": "correspondent", "description": "Correspondent detection"},
            {"value": "document_type", "description": "Document type detection"},
            {"value": "tag", "description": "Tag detection"},
            {"value": "ocr_fix", "description": "OCR post-processing (fix recognition errors)"},
            {"value": "classify", "description": "Document classification (legacy combined)"},
            {"value": "extract", "description": "Custom fields extraction"},
            {"value": "type_specific", "description": "Type-specific extraction (runs after classify)"},
            {"value": "title", "description": "Title generation"},
            {"value": "vision_ocr", "description": "Vision OCR (prompt sent to vision model for text extraction)"},
        ],
    }


@router.get("/{prompt_id}")
async def get_prompt(prompt_id: int):
    with get_session() as session:
        stmt = select(Prompt).where(Prompt.id == prompt_id)
        prompt = session.exec(stmt).first()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
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
        }


@router.post("")
async def create_prompt(prompt: PromptCreate):
    with get_session() as session:
        db_prompt = Prompt(
            name=prompt.name,
            prompt_type=prompt.prompt_type,
            document_type_filter=prompt.document_type_filter,
            system_prompt=prompt.system_prompt,
            user_template=prompt.user_template,
            is_active=prompt.is_active,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(db_prompt)
        return {
            "id": db_prompt.id,
            "name": db_prompt.name,
            "message": "Prompt created successfully",
        }


@router.put("/{prompt_id}")
async def update_prompt(prompt_id: int, prompt: PromptUpdate):
    with get_session() as session:
        stmt = select(Prompt).where(Prompt.id == prompt_id)
        db_prompt = session.exec(stmt).first()
        if not db_prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        
        if prompt.name is not None:
            db_prompt.name = prompt.name
        if prompt.prompt_type is not None:
            db_prompt.prompt_type = prompt.prompt_type
        if prompt.document_type_filter is not None:
            db_prompt.document_type_filter = prompt.document_type_filter
        if prompt.system_prompt is not None:
            db_prompt.system_prompt = prompt.system_prompt
        if prompt.user_template is not None:
            db_prompt.user_template = prompt.user_template
        if prompt.is_active is not None:
            db_prompt.is_active = prompt.is_active
        
        db_prompt.updated_at = datetime.utcnow()
        
        return {
            "id": db_prompt.id,
            "name": db_prompt.name,
            "message": "Prompt updated successfully",
        }


@router.post("/load-samples")
async def load_sample_prompts():
    from pathlib import Path
    import json

    examples_dir = Path(__file__).parent.parent.parent.parent / "examples" / "prompts"
    if not examples_dir.exists():
        raise HTTPException(status_code=404, detail="Examples directory not found")

    created, updated = 0, 0
    with get_session() as session:
        for json_file in sorted(examples_dir.glob("*.json")):
            with open(json_file) as f:
                p = json.load(f)
            stmt = select(Prompt).where(Prompt.name == p["name"])
            existing = session.exec(stmt).first()
            if existing:
                for field in ("prompt_type", "system_prompt", "user_template", "document_type_filter", "is_active"):
                    if field in p:
                        setattr(existing, field, p[field])
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                session.add(Prompt(**p, created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
                created += 1

    return {"created": created, "updated": updated}


@router.delete("/{prompt_id}")
async def delete_prompt(prompt_id: int):
    with get_session() as session:
        stmt = select(Prompt).where(Prompt.id == prompt_id)
        prompt = session.exec(stmt).first()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        session.delete(prompt)
        return {"message": "Prompt deleted successfully"}
