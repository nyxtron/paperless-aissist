from fastapi import APIRouter, HTTPException

from ..services.paperless import PaperlessClient
from ..services.processor import DocumentProcessor
from ..services.scheduler import (
    try_trigger_processing,
    process_tagged_documents as process_tagged_with_state,
    _clear_processing,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/process/{doc_id}")
async def process_document(doc_id: int):
    try:
        paperless = await PaperlessClient.from_config()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    processor = DocumentProcessor(paperless)
    result = await processor.process_document(doc_id)
    
    await paperless.close()
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Processing failed"))
    
    return result


@router.post("/trigger")
async def trigger_processing():
    success, message = try_trigger_processing()
    if not success:
        raise HTTPException(status_code=409, detail=message)
    
    try:
        result = await process_tagged_with_state()
        return result
    except Exception as e:
        _clear_processing()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _clear_processing()


@router.get("/test-connection")
async def test_paperless_connection():
    try:
        paperless = await PaperlessClient.from_config()
        tags = await paperless.get_tags()
        correspondents = await paperless.get_correspondents()
        document_types = await paperless.get_document_types()
        await paperless.close()
        
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
    try:
        paperless = await PaperlessClient.from_config()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        tags = await paperless.get_tags()
        correspondents = await paperless.get_correspondents()
        document_types = await paperless.get_document_types()
        await paperless.close()
        
        return {
            "tags": [{"id": t["id"], "name": t["name"]} for t in tags],
            "correspondents": [{"id": c["id"], "name": c["name"]} for c in correspondents],
            "document_types": [{"id": dt["id"], "name": dt["name"]} for dt in document_types],
        }
    except Exception as e:
        await paperless.close()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tagged")
async def get_tagged_documents():
    from ..database import get_session
    from ..models import Config
    from sqlmodel import select
    
    process_tag_name = None
    with get_session() as session:
        stmt = select(Config).where(Config.key == "process_tag")
        config = session.exec(stmt).first()
        if config:
            process_tag_name = config.value
    
    if not process_tag_name:
        return {"documents": [], "error": "Process tag not configured. Please set 'process_tag' in configuration."}
    
    try:
        paperless = await PaperlessClient.from_config()
    except ValueError as e:
        return {"documents": [], "error": f"Paperless config error: {str(e)}"}
    
    try:
        tags = await paperless.get_tags()
        tags_by_name = {t["name"]: t["id"] for t in tags}
        tag_id = tags_by_name.get(process_tag_name)
        
        if not tag_id:
            return {"documents": [], "error": f"Tag '{process_tag_name}' not found in Paperless"}
        
        docs = await paperless.list_documents(tags=[tag_id], limit=100)
        await paperless.close()
        
        documents = []
        for doc in docs:
            documents.append({
                "id": doc.get("id"),
                "title": doc.get("title"),
                "created": doc.get("created"),
                "added": doc.get("added"),
                "tags": doc.get("tags", []),
            })
        
        return {"documents": documents, "process_tag": process_tag_name, "process_tag_id": tag_id}
    except Exception as e:
        await paperless.close()
        return {"documents": [], "error": str(e)}


@router.get("/chat-list")
async def get_chat_documents():
    """Get documents for chat dropdown - uses process_tag."""
    from ..database import get_session
    from ..models import Config
    from sqlmodel import select
    
    process_tag_name = None
    with get_session() as session:
        stmt = select(Config).where(Config.key == "process_tag")
        config = session.exec(stmt).first()
        if config:
            process_tag_name = config.value
    
    if not process_tag_name:
        return {"documents": [], "error": "Process tag not configured"}
    
    try:
        paperless = await PaperlessClient.from_config()
    except ValueError as e:
        return {"documents": [], "error": f"Paperless config error: {str(e)}"}
    
    try:
        tags = await paperless.get_tags()
        tags_by_name = {t["name"]: t["id"] for t in tags}
        tag_id = tags_by_name.get(process_tag_name)
        
        if not tag_id:
            return {"documents": [], "error": f"Tag '{process_tag_name}' not found in Paperless"}
        
        docs = await paperless.list_documents(tags=[tag_id], limit=100)
        await paperless.close()
        
        documents = []
        for doc in docs:
            documents.append({
                "id": doc.get("id"),
                "title": doc.get("title") or f"Document #{doc.get('id')}",
                "created": doc.get("created"),
            })
        
        return {"documents": documents}
    except Exception as e:
        await paperless.close()
        return {"documents": [], "error": str(e)}


@router.get("/chat/{doc_id}")
async def get_document_for_chat(doc_id: int):
    """Get document content for chat."""
    try:
        paperless = await PaperlessClient.from_config()
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
        
        await paperless.close()
        
        return {
            "id": doc.get("id"),
            "title": doc.get("title"),
            "content": content[:50000],
            "created": doc.get("created"),
        }
    except Exception as e:
        await paperless.close()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/chat")
async def chat_with_document(message: str, doc_id: int):
    """Chat with a document."""
    try:
        paperless = await PaperlessClient.from_config()
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
        
        await paperless.close()
        
        from ..services.llm_handler import LLMHandler
        llm = await LLMHandler.from_config(for_vision=False)
        
        system_prompt = """You are a helpful assistant that answers questions about a document.
Use the provided document content to answer questions accurately.
If the answer is not in the document, say so."""
        
        user_prompt = f"""Document title: {doc.get('title', 'Unknown')}

Document content:
{content[:40000]}

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
        await paperless.close()
        raise HTTPException(status_code=400, detail=str(e))
