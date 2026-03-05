import asyncio
import json
import time
import re
from typing import Optional, Any
from datetime import datetime
from sqlmodel import select

from ..database import get_session
from ..models import Config, Prompt, ProcessingLog, TagCache, CorrespondentCache, DocumentTypeCache
from .paperless import PaperlessClient
from .llm_handler import LLMHandler
from .vision import VisionPipeline

_in_flight_docs: set[int] = set()
_in_flight_lock = asyncio.Lock()


class DocumentProcessor:
    def __init__(self, paperless: PaperlessClient):
        self.paperless = paperless
    
    @staticmethod
    def _parse_classify_response(response: str) -> dict:
        """Parse plain text classify response."""
        result = {}
        
        match = re.search(r'Correspondent:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
        if match:
            result["correspondent"] = match.group(1).strip()
        
        match = re.search(r'Document type:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
        if match:
            result["document_type"] = match.group(1).strip()
        
        match = re.search(r'Tags:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
        if match:
            tags_str = match.group(1).strip()
            result["tags"] = [t.strip() for t in tags_str.split(',') if t.strip()]
        
        return result
    
    @staticmethod
    async def _get_config(key: str, default: Optional[str] = None) -> Optional[str]:
        with get_session() as session:
            stmt = select(Config).where(Config.key == key)
            config = session.exec(stmt).first()
            return config.value if config else default
    
    @staticmethod
    def _get_all_prompts() -> list[dict]:
        with get_session() as session:
            stmt = select(Prompt).where(Prompt.is_active == True)
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
                }
                for p in prompts
            ]
    
    async def _fetch_metadata(self) -> dict[str, Any]:
        tags = await self.paperless.get_tags()
        correspondents = await self.paperless.get_correspondents()
        document_types = await self.paperless.get_document_types()
        
        metadata = {
            "tags": [{"id": t["id"], "name": t["name"]} for t in tags],
            "correspondents": [{"id": c["id"], "name": c["name"]} for c in correspondents],
            "document_types": [{"id": dt["id"], "name": dt["name"]} for dt in document_types],
            "custom_fields": [],
        }

        try:
            custom_fields = await self.paperless.get_custom_fields()
            metadata["custom_fields"] = [{"id": cf["id"], "name": cf["name"], "data_type": cf.get("data_type", "string")} for cf in custom_fields]
        except Exception:
            pass

        return metadata
    
    def _build_lists_for_prompt(self, metadata: dict[str, Any]) -> str:
        tags_list = ", ".join([f'"{t["name"]}"' for t in metadata["tags"]])
        correspondents_list = ", ".join([f'"{c["name"]}"' for c in metadata["correspondents"]])
        document_types_list = ", ".join([f'"{dt["name"]}"' for dt in metadata["document_types"]])
        custom_fields_list = ", ".join([f'{cf["name"]} ({cf.get("data_type", "string")})' for cf in metadata.get("custom_fields", [])])
        
        return f"""Available Tags: [{tags_list}]
Available Correspondents: [{correspondents_list}]
Available Document Types: [{document_types_list}]
Available Custom Fields: [{custom_fields_list}]"""
    
    def _build_custom_fields_list(self, metadata: dict[str, Any]) -> str:
        return ", ".join([f'{cf["name"]}' for cf in metadata.get("custom_fields", [])])
    
    def _substitute_variables(
        self,
        template: str,
        content: str,
        metadata: dict[str, Any],
    ) -> str:
        result = template
        result = result.replace("{content}", content[:10000])
        result = result.replace("{title}", metadata.get("title", ""))
        result = result.replace("{correspondents_list}", ", ".join([f'"{c["name"]}"' for c in metadata["correspondents"]]))
        result = result.replace("{tags_list}", ", ".join([f'"{t["name"]}"' for t in metadata["tags"]]))
        result = result.replace("{document_types_list}", ", ".join([f'"{dt["name"]}"' for dt in metadata["document_types"]]))
        result = result.replace("{custom_fields_list}", self._build_custom_fields_list(metadata))
        return result
    
    async def _log_processing(
        self,
        doc_id: int,
        doc_title: Optional[str],
        status: str,
        provider: Optional[str],
        model: Optional[str],
        llm_response: Optional[str],
        error_message: Optional[str],
        processing_time_ms: int,
        log_id: Optional[int] = None,
    ) -> Optional[int]:
        with get_session() as session:
            if log_id:
                # Update existing log entry
                stmt = select(ProcessingLog).where(ProcessingLog.id == log_id)
                log = session.exec(stmt).first()
                if log:
                    log.status = status
                    log.llm_provider = provider
                    log.llm_model = model
                    log.llm_response = llm_response
                    log.error_message = error_message
                    log.processing_time_ms = processing_time_ms
                    log.processed_at = datetime.utcnow()
                return log_id
            else:
                # Create new log entry
                log = ProcessingLog(
                    document_id=doc_id,
                    document_title=doc_title,
                    status=status,
                    llm_provider=provider,
                    llm_model=model,
                    llm_response=llm_response,
                    error_message=error_message,
                    processing_time_ms=processing_time_ms,
                    processed_at=datetime.utcnow(),
                )
                session.add(log)
                session.flush()
                return log.id
    
    async def process_document(self, doc_id: int) -> dict[str, Any]:
        async with _in_flight_lock:
            if doc_id in _in_flight_docs:
                print(f"[Processor] Doc {doc_id} already in flight, skipping")
                return {"success": False, "error": f"Document {doc_id} is already being processed"}
            _in_flight_docs.add(doc_id)

        try:
            return await self._process_document_inner(doc_id)
        finally:
            async with _in_flight_lock:
                _in_flight_docs.discard(doc_id)

    async def _process_document_inner(self, doc_id: int) -> dict[str, Any]:
        start_time = time.time()
        steps = []

        def add_step(name: str, status: str, duration_ms: int, error: Optional[str] = None):
            steps.append({
                "name": name,
                "status": status,
                "duration_ms": duration_ms,
                "error": error,
            })

        try:
            await self.paperless.from_config()
        except ValueError as e:
            return {"success": False, "error": str(e)}
        
        step_start = time.time()
        doc = await self.paperless.get_document(doc_id)
        add_step("Fetch document", "completed", int((time.time() - step_start) * 1000))
        
        log_id = await self._log_processing(
            doc_id=doc_id,
            doc_title=doc.get("title"),
            status="processing",
            provider=None,
            model=None,
            llm_response=None,
            error_message=None,
            processing_time_ms=0,
        )
        
        content = doc.get("content", "").strip() if doc.get("content") else ""
        doc_tags = doc.get("tags", [])
        
        # Get tag names from IDs
        all_tags = await self.paperless.get_tags()
        tag_id_to_name = {t["id"]: t["name"] for t in all_tags}
        doc_tag_names = [tag_id_to_name.get(tid, "") for tid in doc_tags]
        
        vision_enabled = await self._get_config("enable_vision", "false") == "true"
        force_ocr_tag = await self._get_config("force_ocr_tag", "force_ocr")
        force_ocr_fix_tag = await self._get_config("force_ocr_fix_tag", "force-ocr-fix")
        needs_vision = not content or (force_ocr_tag and force_ocr_tag in doc_tag_names) or (force_ocr_fix_tag and force_ocr_fix_tag in doc_tag_names)
        ocr_performed = False
        
        if needs_vision and vision_enabled:
            ocr_start = time.time()
            try:
                vision_pipeline = await VisionPipeline.create()
                pdf_bytes = await self.paperless.get_document_file(doc_id)
                vision_prompt_text = None
                with get_session() as session:
                    stmt = select(Prompt).where(Prompt.prompt_type == "vision_ocr", Prompt.is_active == True)
                    vp = session.exec(stmt).first()
                    if vp:
                        vision_prompt_text = vp.system_prompt
                vision_result = await vision_pipeline.extract_text_from_pdf(pdf_bytes, prompt=vision_prompt_text)
                content = vision_result.get("text", "") or vision_result.get("raw", "")
                ocr_performed = True
                add_step("OCR (Vision)", "completed", int((time.time() - ocr_start) * 1000))
            except Exception as e:
                fallback_enabled = await self._get_config("enable_fallback_ocr", "false") == "true"
                if fallback_enabled:
                    try:
                        pdf_bytes = await self.paperless.get_document_file(doc_id)
                        content = await self._fallback_ocr(pdf_bytes)
                        ocr_performed = True
                        add_step("OCR (Fallback)", "completed", int((time.time() - ocr_start) * 1000))
                    except Exception as fallback_error:
                        add_step("OCR", "failed", int((time.time() - ocr_start) * 1000), str(fallback_error))
                        await self._log_processing(
                            doc_id=doc_id,
                            doc_title=doc.get("title"),
                            status="failed",
                            provider="vision",
                            model="unknown",
                            llm_response=None,
                            error_message=f"Vision OCR failed: {str(e)}, Fallback OCR also failed: {str(fallback_error)}",
                            processing_time_ms=int((time.time() - start_time) * 1000),
                            log_id=log_id,
                        )
                        return {"success": False, "error": f"OCR failed: {str(e)}"}
                else:
                    add_step("OCR (Vision)", "failed", int((time.time() - ocr_start) * 1000), str(e))
                    await self._log_processing(
                        doc_id=doc_id,
                        doc_title=doc.get("title"),
                        status="failed",
                        provider="vision",
                        model="unknown",
                        llm_response=None,
                        error_message=f"Vision OCR failed: {str(e)}, Fallback disabled by configuration",
                        processing_time_ms=int((time.time() - start_time) * 1000),
                        log_id=log_id,
                    )
                    return {"success": False, "error": f"Vision OCR failed: {str(e)}"}
        
        # OCR Post-Processing: Fix OCR errors using LLM
        ocr_fix_enabled = await self._get_config("ocr_post_process", "true") == "true"
        force_ocr_fix_tag = await self._get_config("force_ocr_fix_tag", "force-ocr-fix")
        
        if ocr_performed and content and force_ocr_fix_tag and force_ocr_fix_tag in doc_tag_names:
            if ocr_fix_enabled:
                fix_start = time.time()
                try:
                    ocr_fix_prompts = [p for p in self._get_all_prompts() if p.get("prompt_type") == "ocr_fix"]
                    if ocr_fix_prompts:
                        ocr_fix_prompt = ocr_fix_prompts[0]
                        llm_for_fix = await LLMHandler.from_config(for_vision=False)
                        
                        fix_result = await llm_for_fix.complete(
                            system_prompt=ocr_fix_prompt.get("system_prompt", ""),
                            user_prompt=ocr_fix_prompt.get("user_template", "").replace("{content}", content),
                            json_mode=False,
                        )
                        fixed_content = fix_result.get("text", "").strip() or fix_result.get("raw", "").strip()
                        if fixed_content:
                            content = fixed_content
                            add_step("OCR Fix", "completed", int((time.time() - fix_start) * 1000))
                except Exception as fix_error:
                    add_step("OCR Fix", "failed", int((time.time() - fix_start) * 1000), str(fix_error))
        
        if not content:
            await self._log_processing(
                doc_id=doc_id,
                doc_title=doc.get("title"),
                status="skipped",
                provider=None,
                model=None,
                llm_response=None,
                error_message="No content available and vision not enabled",
                processing_time_ms=int((time.time() - start_time) * 1000),
                log_id=log_id,
            )
            return {"success": False, "error": "No content available"}
        
        metadata = await self._fetch_metadata()
        metadata["title"] = doc.get("title", "")
        prompts = self._get_all_prompts()
        add_step("Fetch metadata", "completed", 0)
        
        llm = await LLMHandler.from_config(for_vision=False)
        
        update_data = {}
        
        if ocr_performed and content:
            update_data["content"] = content
        
        title_prompt = next((p for p in prompts if p.get("prompt_type") == "title"), None)
        title_raw_response = None
        if title_prompt:
            title_start = time.time()
            user_msg = self._substitute_variables(
                title_prompt.get("user_template", ""),
                content,
                metadata,
            )
            title_result = await llm.complete(
                system_prompt=title_prompt.get("system_prompt", ""),
                user_prompt=user_msg,
                json_mode=False,
            )
            title_text = title_result.get("text", "").strip() or title_result.get("raw", "").strip()
            title_raw_response = title_result
            if title_text:
                update_data["title"] = title_text
            add_step("Extract title", "completed", int((time.time() - title_start) * 1000))
        
        correspondent_prompt = next((p for p in prompts if p.get("prompt_type") == "correspondent"), None)
        document_type_prompt = next((p for p in prompts if p.get("prompt_type") == "document_type"), None)
        tag_prompt = next((p for p in prompts if p.get("prompt_type") == "tag"), None)
        classify_prompt = next((p for p in prompts if p.get("prompt_type") == "classify"), None)

        detected_type = None
        classification_result = None
        use_individual = correspondent_prompt or document_type_prompt or tag_prompt

        if use_individual:
            # Individual pipeline stages
            if correspondent_prompt:
                corr_start = time.time()
                user_msg = self._substitute_variables(
                    correspondent_prompt.get("user_template", ""), content, metadata
                )
                corr_result = await llm.complete(
                    system_prompt=correspondent_prompt.get("system_prompt", ""),
                    user_prompt=user_msg,
                    json_mode=False,
                )
                corr_text = corr_result.get("text", "").strip() or corr_result.get("raw", "").strip()
                if corr_text and corr_text.lower() != "none":
                    corr_match = next(
                        (c["id"] for c in metadata["correspondents"] if c["name"].lower() == corr_text.lower()),
                        None,
                    )
                    if corr_match:
                        update_data["correspondent"] = corr_match
                add_step("Detect correspondent", "completed", int((time.time() - corr_start) * 1000))

            if document_type_prompt:
                dt_start = time.time()
                user_msg = self._substitute_variables(
                    document_type_prompt.get("user_template", ""), content, metadata
                )
                dt_result = await llm.complete(
                    system_prompt=document_type_prompt.get("system_prompt", ""),
                    user_prompt=user_msg,
                    json_mode=False,
                )
                dt_text = dt_result.get("text", "").strip() or dt_result.get("raw", "").strip()
                if dt_text and dt_text.lower() != "none":
                    dt_match = next(
                        (dt["id"] for dt in metadata["document_types"] if dt["name"].lower() == dt_text.lower()),
                        None,
                    )
                    if dt_match:
                        update_data["document_type"] = dt_match
                    detected_type = dt_text
                add_step("Detect document type", "completed", int((time.time() - dt_start) * 1000))

            if tag_prompt:
                tag_start = time.time()
                user_msg = self._substitute_variables(
                    tag_prompt.get("user_template", ""), content, metadata
                )
                tag_result = await llm.complete(
                    system_prompt=tag_prompt.get("system_prompt", ""),
                    user_prompt=user_msg,
                    json_mode=False,
                )
                tag_text = tag_result.get("text", "").strip() or tag_result.get("raw", "").strip()
                if tag_text and tag_text.lower() != "none":
                    blacklist_raw = await self._get_config("tag_blacklist", "")
                    blacklist = [t.strip().lower() for t in blacklist_raw.split(",") if t.strip()]
                    tag_names = [t.strip() for t in tag_text.split(",") if t.strip()]
                    tag_ids = []
                    for tag_name in tag_names:
                        if blacklist and tag_name.lower() in blacklist:
                            continue
                        tag_match = next(
                            (t["id"] for t in metadata["tags"] if t["name"].lower() == tag_name.lower()),
                            None,
                        )
                        if tag_match:
                            tag_ids.append(tag_match)
                    if tag_ids:
                        update_data["tags"] = tag_ids
                add_step("Detect tags", "completed", int((time.time() - tag_start) * 1000))

        elif classify_prompt:
            # Legacy combined classify fallback
            classification_result = None
            classify_start = time.time()
            user_msg = self._substitute_variables(
                classify_prompt.get("user_template", ""), content, metadata
            )
            classification_result = await llm.complete(
                system_prompt=classify_prompt.get("system_prompt", ""),
                user_prompt=user_msg,
                json_mode=False,
            )

            if classification_result and isinstance(classification_result, dict):
                if "text" in classification_result:
                    plain_text = classification_result.get("text", "")
                    parsed = self._parse_classify_response(plain_text)
                    if parsed:
                        classification_result = parsed
                elif "raw" in classification_result:
                    plain_text = classification_result.get("raw", "")
                    parsed = self._parse_classify_response(plain_text)
                    if parsed:
                        classification_result = parsed

            add_step("Analyze document", "completed", int((time.time() - classify_start) * 1000))

            if classification_result:
                detected_type = classification_result.get("document_type")

                if "title" in classification_result and classification_result["title"]:
                    update_data["title"] = classification_result["title"]

                if "correspondent" in classification_result and classification_result["correspondent"]:
                    corr_name = classification_result["correspondent"]
                    corr_match = next(
                        (c["id"] for c in metadata["correspondents"] if c["name"].lower() == corr_name.lower()),
                        None,
                    )
                    if corr_match:
                        update_data["correspondent"] = corr_match

                if "document_type" in classification_result and classification_result["document_type"]:
                    doc_type_name = classification_result["document_type"]
                    doc_type_match = next(
                        (dt["id"] for dt in metadata["document_types"] if dt["name"].lower() == doc_type_name.lower()),
                        None,
                    )
                    if doc_type_match:
                        update_data["document_type"] = doc_type_match

                if "tags" in classification_result and classification_result["tags"]:
                    tag_names = classification_result["tags"] if isinstance(classification_result["tags"], list) else [classification_result["tags"]]
                    blacklist_raw = await self._get_config("tag_blacklist", "")
                    blacklist = [t.strip().lower() for t in blacklist_raw.split(",") if t.strip()]
                    tag_ids = []
                    for tag_name in tag_names:
                        if blacklist and tag_name.lower() in blacklist:
                            continue
                        tag_match = next(
                            (t["id"] for t in metadata["tags"] if t["name"].lower() == tag_name.lower()),
                            None,
                        )
                        if tag_match:
                            tag_ids.append(tag_match)
                    if tag_ids:
                        update_data["tags"] = tag_ids
        
        type_specific_prompt = None
        if detected_type:
            type_specific_prompt = next(
                (p for p in prompts 
                 if p.get("prompt_type") == "type_specific" 
                 and p.get("document_type_filter") 
                 and p.get("document_type_filter", "").lower() == detected_type.lower()),
                None
            )
        
        custom_fields_start = time.time()
        extract_prompt = next((p for p in prompts if p.get("prompt_type") == "extract"), None)
        combined_fields: dict[str, str] = {}

        def _extract_fields_from_result(result: dict) -> dict[str, str]:
            """Parse an LLM custom fields result into a flat {field_name: value} dict."""
            fields = {}
            items = []
            if "custom_fields" in result:
                items = result["custom_fields"]
            elif "extract" in result:
                for k, v in result["extract"].items():
                    if v:
                        fields[k.lower()] = v
                return fields
            elif "field" in result and "value" in result:
                items = [result]
            for key, value in result.items():
                if key not in ("custom_fields", "extract") and isinstance(value, str) and value:
                    fields[key.lower()] = value
            for item in items:
                if isinstance(item, dict) and item.get("field") and item.get("value"):
                    fields[str(item["field"]).lower()] = item["value"]
            return fields

        if extract_prompt:
            user_msg = self._substitute_variables(
                extract_prompt.get("user_template", ""), content, metadata
            )
            extract_result = await llm.complete(
                system_prompt=extract_prompt.get("system_prompt", ""),
                user_prompt=user_msg,
                json_mode=True,
            )
            if extract_result and isinstance(extract_result, dict):
                combined_fields.update(_extract_fields_from_result(extract_result))

        if type_specific_prompt:
            user_msg = self._substitute_variables(
                type_specific_prompt.get("user_template", ""), content, metadata
            )
            type_result = await llm.complete(
                system_prompt=type_specific_prompt.get("system_prompt", ""),
                user_prompt=user_msg,
                json_mode=True,
            )
            if type_result and isinstance(type_result, dict):
                combined_fields.update(_extract_fields_from_result(type_result))

        if extract_prompt or type_specific_prompt:
            add_step("Extract custom fields", "completed", int((time.time() - custom_fields_start) * 1000))
        
        if combined_fields:
            paperless_custom_fields = await self.paperless.get_custom_fields()
            field_name_to_id = {cf["name"].lower(): cf["id"] for cf in paperless_custom_fields}
            converted_fields = []
            for field_name, field_value in combined_fields.items():
                field_id = field_name_to_id.get(field_name)
                if field_id and field_value:
                    converted_fields.append({"field": field_id, "value": field_value})
            if converted_fields:
                update_data["custom_fields"] = converted_fields
        
        save_start = time.time()

        # Merge tag swap with any LLM-detected tags into a single update
        process_tag_name = await self._get_config("process_tag")
        processed_tag_name = await self._get_config("processed_tag")

        tags_by_name = {t["name"]: t["id"] for t in metadata.get("tags", [])}
        process_tag_id = tags_by_name.get(process_tag_name) if process_tag_name else None
        processed_tag_id = tags_by_name.get(processed_tag_name) if processed_tag_name else None

        existing_tag_ids = list(doc.get("tags", []))
        if process_tag_id and process_tag_id in existing_tag_ids:
            existing_tag_ids.remove(process_tag_id)
        for tid in update_data.pop("tags", []):
            if tid not in existing_tag_ids:
                existing_tag_ids.append(tid)
        if processed_tag_id and processed_tag_id not in existing_tag_ids:
            existing_tag_ids.append(processed_tag_id)
        update_data["tags"] = existing_tag_ids

        if update_data:
            try:
                await self.paperless.update_document(doc_id, **update_data)
            except Exception as e:
                error_detail = str(e)
                if hasattr(e, "response") and e.response is not None:
                    try:
                        error_detail = f"{error_detail}: {e.response.text}"
                    except Exception:
                        pass
                await self._log_processing(
                    doc_id=doc_id,
                    doc_title=doc.get("title"),
                    status="failed",
                    provider=llm.provider,
                    model=llm.model,
                    llm_response=None,
                    error_message=f"Paperless update failed: {error_detail}",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    log_id=log_id,
                )
                return {"success": False, "error": f"Paperless update failed: {error_detail}"}

        add_step("Save changes", "completed", int((time.time() - save_start) * 1000))
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        await self._log_processing(
            doc_id=doc_id,
            doc_title=doc.get("title"),
            status="success",
            provider=llm.provider,
            model=llm.model,
            llm_response=json.dumps({
                "title": title_raw_response,
                "classification": classification_result,
                "custom_fields": combined_fields,
            }),
            error_message=None,
            processing_time_ms=processing_time_ms,
            log_id=log_id,
        )
        
        return {
            "success": True,
            "document_id": doc_id,
            "title": doc.get("title"),
            "updates": update_data,
            "processing_time_ms": processing_time_ms,
            "steps": steps,
        }
    
    async def process_tagged_documents(self) -> dict[str, Any]:
        process_tag_name = await self._get_config("process_tag")
        
        if not process_tag_name:
            return {"success": False, "error": "Process tag not configured. Please set 'process_tag' in configuration."}
        
        try:
            await self.paperless.from_config()
        except ValueError as e:
            return {"success": False, "error": str(e)}
        
        # Get tags and resolve tag name to ID
        tags = await self.paperless.get_tags()
        tags_by_name = {t["name"]: t["id"] for t in tags}
        process_tag_id = tags_by_name.get(process_tag_name)
        
        if not process_tag_id:
            return {"success": False, "error": f"Tag '{process_tag_name}' not found in Paperless"}
        
        documents = await self.paperless.list_documents(tags=[process_tag_id])
        
        results = []
        for doc in documents:
            result = await self.process_document(doc["id"])
            results.append(result)
        
        return {
            "success": True,
            "processed": len(results),
            "results": results,
        }
    
    async def _fallback_ocr(self, pdf_bytes: bytes) -> str:
        """Fallback OCR using pytesseract if vision model fails."""
        import fitz
        import io
        from PIL import Image
        import pytesseract
        
        text_parts = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            text = pytesseract.image_to_string(img)
            text_parts.append(text)
        
        doc.close()
        return "\n".join(text_parts)
