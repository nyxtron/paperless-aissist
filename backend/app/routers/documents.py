"""Document processing endpoints: trigger, chat, tag listing, and preview."""

from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel
from starlette.requests import Request

from ..limiter import limiter

from ..services.paperless import PaperlessClient
from ..services.paperless_manager import PaperlessClientManager
from ..services.processor import DocumentProcessor
from ..services.scheduler import (
    try_trigger_processing,
    process_tagged_documents as process_tagged_with_state,
    process_modular_tagged_documents as process_modular_with_state,
    _clear_processing,
)
from ..constants import CHAT_CONTENT_LIMIT, CHAT_HISTORY_LIMIT

router = APIRouter(prefix="/api/documents", tags=["documents"])


class ProcessRequest(BaseModel):
    document_id: int
    force: bool = False


@router.post("/process")
async def process_document(data: ProcessRequest = Body(...)):
    """Process a single document by ID through the AI pipeline."""
    try:
        paperless = await PaperlessClientManager.get_client()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    processor = DocumentProcessor(paperless)

    result = await processor.process_document(data.document_id, force=data.force)

    if not result.get("success"):
        raise HTTPException(
            status_code=500, detail=result.get("error", "Processing failed")
        )

    return result


@router.get("/search")
async def search_documents(query: str = Query(..., max_length=500)):
    """Search documents in Paperless by query string."""
    try:
        paperless = await PaperlessClientManager.get_client()
    except ValueError as e:
        return {"results": [], "error": f"Paperless config error: {str(e)}"}

    try:
        docs = await paperless.list_documents(search=query)

        results = [
            {
                "id": doc.get("id"),
                "title": doc.get("title"),
                "created": doc.get("created"),
            }
            for doc in docs[:5]
        ]
        return {"results": results}
    except Exception as e:
        await paperless.close()
        return {"results": [], "error": str(e)}


@router.get("/preview/{doc_id}")
async def get_preview(doc_id: int):
    """Preview what ai-process would do for a document - runs all steps EXCEPT OCR/OCR-fix."""
    try:
        paperless = await PaperlessClientManager.get_client()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        processor = DocumentProcessor(paperless)
        result = await processor.process_document_preview(doc_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger")
async def trigger_processing():
    """Manually trigger processing of all tagged documents (legacy + modular)."""
    success, message = try_trigger_processing()
    if not success:
        raise HTTPException(status_code=409, detail=message)

    try:
        legacy = await process_tagged_with_state()
        modular = await process_modular_with_state()
        return {
            "success": True,
            "processed": legacy.get("processed", 0) + modular.get("processed", 0),
            "results": legacy.get("results", []) + modular.get("results", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _clear_processing()


@router.get("/test-connection")
async def test_paperless_connection():
    try:
        paperless = await PaperlessClientManager.get_client()
        tags = await paperless.get_tags()
        correspondents = await paperless.get_correspondents()
        document_types = await paperless.get_document_types()

        return {
            "success": True,
            "message": "Connection successful",
            "stats": {
                "tags": len(tags),
                "correspondents": len(correspondents),
                "document_types": len(document_types),
            },
            "available_tags": [{"id": t["id"], "name": t["name"]} for t in tags],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tags")
async def get_paperless_tags():
    """Return all Paperless tags, correspondents, and document types."""
    try:
        paperless = await PaperlessClientManager.get_client()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        tags = await paperless.get_tags()
        correspondents = await paperless.get_correspondents()
        document_types = await paperless.get_document_types()

        return {
            "tags": [{"id": t["id"], "name": t["name"]} for t in tags],
            "correspondents": [
                {"id": c["id"], "name": c["name"]} for c in correspondents
            ],
            "document_types": [
                {"id": dt["id"], "name": dt["name"]} for dt in document_types
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tagged")
async def get_tagged_documents():
    from ..database import get_async_session
    from ..models import Config
    from ..services.processor import DocumentProcessor
    from sqlmodel import select

    process_tag_name = None
    async with get_async_session() as session:
        stmt = select(Config).where(Config.key == "process_tag")
        config = await session.exec(stmt)
        config = config.first()
        if config:
            process_tag_name = config.value

    try:
        paperless = await PaperlessClientManager.get_client()
    except ValueError as e:
        return {"documents": [], "error": f"Paperless config error: {str(e)}"}

    try:
        tags = await paperless.get_tags()
        tags_by_name = {t["name"]: t["id"] for t in tags}

        merged: dict[int, dict] = {}

        # Fetch docs tagged with process_tag
        process_tag_id = None
        if process_tag_name:
            process_tag_id = tags_by_name.get(process_tag_name)
            if process_tag_id:
                for doc in await paperless.list_documents(tags=[process_tag_id]):
                    merged[doc["id"]] = doc

        # Fetch docs tagged with any modular trigger tag
        modular_tag_map = await DocumentProcessor._get_modular_tag_map()
        for tag_name in modular_tag_map.values():
            tag_id = tags_by_name.get(tag_name)
            if tag_id:
                for doc in await paperless.list_documents(tags=[tag_id]):
                    merged[doc["id"]] = doc

        documents = [
            {
                "id": doc.get("id"),
                "title": doc.get("title"),
                "created": doc.get("created"),
                "added": doc.get("added"),
                "tags": doc.get("tags", []),
            }
            for doc in merged.values()
        ]

        return {
            "documents": documents,
            "process_tag": process_tag_name,
            "process_tag_id": process_tag_id,
        }
    except Exception as e:
        return {"documents": [], "error": str(e)}


@router.get("/chat-list")
async def get_chat_documents():
    """Get documents for chat dropdown - uses process_tag."""
    from ..database import get_async_session
    from ..models import Config
    from sqlmodel import select

    process_tag_name = None
    async with get_async_session() as session:
        stmt = select(Config).where(Config.key == "process_tag")
        config = await session.exec(stmt)
        config = config.first()
        if config:
            process_tag_name = config.value

    if not process_tag_name:
        return {"documents": [], "error": "Process tag not configured"}

    try:
        paperless = await PaperlessClientManager.get_client()
    except ValueError as e:
        return {"documents": [], "error": f"Paperless config error: {str(e)}"}

    try:
        tags = await paperless.get_tags()
        tags_by_name = {t["name"]: t["id"] for t in tags}
        tag_id = tags_by_name.get(process_tag_name)

        if not tag_id:
            return {
                "documents": [],
                "error": f"Tag '{process_tag_name}' not found in Paperless",
            }

        docs = await paperless.list_documents(tags=[tag_id])

        documents = []
        for doc in docs:
            documents.append(
                {
                    "id": doc.get("id"),
                    "title": doc.get("title") or f"Document #{doc.get('id')}",
                    "created": doc.get("created"),
                }
            )

        return {"documents": documents}
    except Exception as e:
        return {"documents": [], "error": str(e)}


@router.get("/chat/{doc_id}")
async def get_document_for_chat(doc_id: int):
    """Get document content for chat."""
    try:
        paperless = await PaperlessClientManager.get_client()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        doc = await paperless.get_document(doc_id)
        content = doc.get("content", "").strip() if doc.get("content") else ""

        if not content:
            pdf_bytes = await paperless.get_document_file(doc_id)
            from ..services.vision import VisionPipeline

            vision_pipeline = await VisionPipeline.create()
            vision_result = await vision_pipeline.extract_text_from_pdf(pdf_bytes)
            content = vision_result.get("text", "") or vision_result.get("raw", "")

        return {
            "id": doc.get("id"),
            "title": doc.get("title"),
            "content": content[:CHAT_HISTORY_LIMIT],
            "created": doc.get("created"),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/chat")
@limiter.limit("10/minute")
async def chat_with_document(
    request: Request, doc_id: int, message: str = Query(..., max_length=10000)
):
    """Chat with a document."""
    try:
        paperless = await PaperlessClientManager.get_client()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        doc = await paperless.get_document(doc_id)
        content = doc.get("content", "").strip() if doc.get("content") else ""

        if not content:
            pdf_bytes = await paperless.get_document_file(doc_id)
            from ..services.vision import VisionPipeline

            vision_pipeline = await VisionPipeline.create()
            vision_result = await vision_pipeline.extract_text_from_pdf(pdf_bytes)
            content = vision_result.get("text", "") or vision_result.get("raw", "")

        from ..services.llm_handler import LLMHandlerManager

        llm = await LLMHandlerManager.get_handler(for_vision=False)

        system_prompt = """You are a helpful assistant that answers questions about a document.
Use the provided document content to answer questions accurately.
If the answer is not in the document, say so."""

        user_prompt = f"""Document title: {doc.get("title", "Unknown")}

Document content:
{content[:CHAT_CONTENT_LIMIT]}

Question: {message}

Answer the question based on the document content above."""

        result = await llm.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=False,
        )

        response_text = result.get("text", "").strip() or result.get("raw", "").strip()

        return {"response": response_text}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
