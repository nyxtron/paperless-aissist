"""Document processing pipeline.

Orchestrates step-based AI processing of Paperless documents: OCR, title generation,
correspondent/dtype/tag detection, custom field extraction, and tag lifecycle management.
"""

import asyncio
import json
import logging
import time
import re

import httpx
from typing import Optional, Any
from datetime import datetime, timezone
from sqlmodel import select

logger = logging.getLogger(__name__)

MODULAR_TAG_DEFAULTS: dict[str, str] = {
    "modular_tag_ocr": "ai-ocr",
    "modular_tag_ocr_fix": "ai-ocr-fix",
    "modular_tag_date": "ai-date",
    "modular_tag_title": "ai-title",
    "modular_tag_correspondent": "ai-correspondent",
    "modular_tag_document_type": "ai-document-type",
    "modular_tag_tags": "ai-tags",
    "modular_tag_fields": "ai-fields",
    "modular_tag_process": "ai-process",
}

from ..database import get_async_session
from ..models import (
    Config,
    Prompt,
    ProcessingLog,
)
from .paperless import PaperlessClient
from .llm_handler import LLMHandlerManager
from ..exceptions import LLMUnavailableError
from ..constants import CONTENT_TRUNCATION_LIMIT, TITLE_MAX_LENGTH
from .vision import VisionPipeline
from .config_cache import ConfigCache

_in_flight_docs: set[int] = set()
_in_flight_lock = asyncio.Lock()


class DocumentProcessor:
    """Coordinates step-based AI document processing.

    Runs a configurable pipeline of steps (OCR, title, correspondent, dtype, tags,
    fields, modular tags) against a single Paperless document.
    """

    def __init__(self, paperless: PaperlessClient):
        """Initialize with a Paperless client; steps are built lazily."""
        self.paperless = paperless
        self._steps: list | None = None

    async def _get_config_dict(self) -> dict[str, str]:
        """Return the full config dict from the cache."""
        from .config_cache import ConfigCache

        cache = await ConfigCache.get_instance()
        return await cache.get_all()

    async def _build_steps(self) -> list:
        """Lazily build and cache the ordered list of processing steps."""
        if self._steps is not None:
            return self._steps
        from .steps import (
            OCRStep,
            OCRFixStep,
            DateStep,
            TitleStep,
            CorrespondentStep,
            DocumentTypeStep,
            TagsStep,
            FieldsStep,
        )

        config = await self._get_config_dict()
        steps = [
            await OCRStep.from_config(config),
            await OCRFixStep.from_config(config),
            await DateStep.from_config(config),
            await TitleStep.from_config(config),
            await CorrespondentStep.from_config(config),
            await DocumentTypeStep.from_config(config),
            await TagsStep.from_config(config),
            await FieldsStep.from_config(config),
        ]
        self._steps = steps
        return steps

    @staticmethod
    def _parse_classify_response(response: str) -> dict:
        """Parse plain text classify response."""
        result = {}

        match = re.search(r"Correspondent:\s*(.+?)(?:\n|$)", response, re.IGNORECASE)
        if match:
            result["correspondent"] = match.group(1).strip()

        match = re.search(r"Document type:\s*(.+?)(?:\n|$)", response, re.IGNORECASE)
        if match:
            result["document_type"] = match.group(1).strip()

        match = re.search(r"Tags:\s*(.+?)(?:\n|$)", response, re.IGNORECASE)
        if match:
            tags_str = match.group(1).strip()
            result["tags"] = [t.strip() for t in tags_str.split(",") if t.strip()]

        return result

    @staticmethod
    async def _get_config(key: str, default: Optional[str] = None) -> Optional[str]:
        cache = await ConfigCache.get_instance()
        return await cache.get(key, default or "")

    @staticmethod
    async def _get_all_prompts() -> list[dict]:
        async with get_async_session() as session:
            stmt = select(Prompt).where(Prompt.is_active.is_(True))
            prompts = await session.exec(stmt)
            prompts = prompts.all()
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
            "correspondents": [
                {"id": c["id"], "name": c["name"]} for c in correspondents
            ],
            "document_types": [
                {"id": dt["id"], "name": dt["name"]} for dt in document_types
            ],
            "custom_fields": [],
        }

        try:
            custom_fields = await self.paperless.get_custom_fields()
            metadata["custom_fields"] = [
                {
                    "id": cf["id"],
                    "name": cf["name"],
                    "data_type": cf.get("data_type", "string"),
                }
                for cf in custom_fields
            ]
        except Exception:
            pass

        return metadata

    def _build_lists_for_prompt(self, metadata: dict[str, Any]) -> str:
        tags_list = ", ".join([f'"{t["name"]}"' for t in metadata["tags"]])
        correspondents_list = ", ".join(
            [f'"{c["name"]}"' for c in metadata["correspondents"]]
        )
        document_types_list = ", ".join(
            [f'"{dt["name"]}"' for dt in metadata["document_types"]]
        )
        custom_fields_list = ", ".join(
            [
                f"{cf['name']} ({cf.get('data_type', 'string')})"
                for cf in metadata.get("custom_fields", [])
            ]
        )

        return f"""Available Tags: [{tags_list}]
Available Correspondents: [{correspondents_list}]
Available Document Types: [{document_types_list}]
Available Custom Fields: [{custom_fields_list}]"""

    def _build_custom_fields_list(self, metadata: dict[str, Any]) -> str:
        return ", ".join([f"{cf['name']}" for cf in metadata.get("custom_fields", [])])

    def _substitute_variables(
        self,
        template: str,
        content: str,
        metadata: dict[str, Any],
    ) -> str:
        result = template
        result = result.replace("{content}", content[:CONTENT_TRUNCATION_LIMIT])
        result = result.replace("{title}", metadata.get("title", ""))
        result = result.replace(
            "{correspondents_list}",
            ", ".join([f'"{c["name"]}"' for c in metadata["correspondents"]]),
        )
        result = result.replace(
            "{tags_list}", ", ".join([f'"{t["name"]}"' for t in metadata["tags"]])
        )
        result = result.replace(
            "{document_types_list}",
            ", ".join([f'"{dt["name"]}"' for dt in metadata["document_types"]]),
        )
        result = result.replace(
            "{custom_fields_list}", self._build_custom_fields_list(metadata)
        )
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
        async with get_async_session() as session:
            if log_id:
                stmt = select(ProcessingLog).where(ProcessingLog.id == log_id)
                log = await session.exec(stmt)
                log = log.first()
                if log:
                    log.status = status
                    log.llm_provider = provider
                    log.llm_model = model
                    log.llm_response = llm_response
                    log.error_message = error_message
                    log.processing_time_ms = processing_time_ms
                    log.processed_at = datetime.now(timezone.utc)
                return log_id
            else:
                log = ProcessingLog(
                    document_id=doc_id,
                    document_title=doc_title,
                    status=status,
                    llm_provider=provider,
                    llm_model=model,
                    llm_response=llm_response,
                    error_message=error_message,
                    processing_time_ms=processing_time_ms,
                    processed_at=datetime.now(timezone.utc),
                )
                session.add(log)
                await session.flush()
                return log.id

    async def _delete_log(self, log_id: int) -> None:
        async with get_async_session() as session:
            stmt = select(ProcessingLog).where(ProcessingLog.id == log_id)
            log = await session.exec(stmt)
            log = log.first()
            if log:
                await session.delete(log)

    async def _resolve_proposed_changes(
        self,
        proposed: dict[str, Any],
        all_tags: list[dict],
        all_correspondents: list[dict],
        all_document_types: list[dict],
        all_custom_fields: list[dict],
    ) -> dict[str, Any]:
        tag_id_to_name = {t["id"]: t["name"] for t in all_tags}
        corr_id_to_name = {c["id"]: c["name"] for c in all_correspondents}
        type_id_to_name = {t["id"]: t["name"] for t in all_document_types}
        cf_id_to_name = {cf["id"]: cf["name"] for cf in all_custom_fields}
        resolved = dict(proposed)

        if "tags" in resolved and isinstance(resolved["tags"], list):
            resolved["tags"] = [
                {"id": tid, "name": tag_id_to_name.get(tid, f"tag:{tid}")}
                for tid in resolved["tags"]
            ]

        if "correspondent" in resolved and isinstance(resolved["correspondent"], int):
            resolved["correspondent"] = {
                "id": resolved["correspondent"],
                "name": corr_id_to_name.get(
                    resolved["correspondent"], f"corr:{resolved['correspondent']}"
                ),
            }

        if "document_type" in resolved and isinstance(resolved["document_type"], int):
            resolved["document_type"] = {
                "id": resolved["document_type"],
                "name": type_id_to_name.get(
                    resolved["document_type"], f"type:{resolved['document_type']}"
                ),
            }

        if "custom_fields" in resolved and isinstance(resolved["custom_fields"], list):
            resolved["custom_fields"] = [
                {
                    "id": cf["field"],
                    "name": cf_id_to_name.get(cf["field"], f"field:{cf['field']}"),
                    "value": cf["value"],
                }
                for cf in resolved["custom_fields"]
            ]

        return resolved

    async def process_document(
        self, doc_id: int, force: bool = False
    ) -> dict[str, Any]:
        async with _in_flight_lock:
            if doc_id in _in_flight_docs:
                logger.info(f"Doc {doc_id} already in flight, skipping")
                return {
                    "success": False,
                    "error": f"Document {doc_id} is already being processed",
                }
            _in_flight_docs.add(doc_id)

        try:
            return await self._process_document_step_based(doc_id)
        finally:
            try:
                from .scheduler import mark_document_finished

                mark_document_finished(doc_id)
            except Exception as state_error:
                logger.debug("Could not clear active document state: %s", state_error)
            async with _in_flight_lock:
                _in_flight_docs.discard(doc_id)

    async def process_document_preview(self, doc_id: int) -> dict[str, Any]:
        """Runs the ai-process pipeline (all steps EXCEPT OCR/OCR-fix) and returns proposed changes without modifying Paperless."""
        start_time = time.time()
        config_dict = await self._get_config_dict()

        from .steps import (
            TitleStep,
            CorrespondentStep,
            DocumentTypeStep,
            TagsStep,
            FieldsStep,
        )

        # A preview must not write to Paperless. The correspondent step is the
        # only one that can (creating a new correspondent), so force its opt-in
        # flag off here regardless of the live config — otherwise a preview would
        # leave an orphaned correspondent behind, contradicting what the
        # docstring, the MCP tool and the UI all promise.
        preview_config = {**config_dict, "correspondent_create_new": "false"}
        steps = [
            await TitleStep.from_config(config_dict),
            await CorrespondentStep.from_config(preview_config),
            await DocumentTypeStep.from_config(config_dict),
            await TagsStep.from_config(config_dict),
            await FieldsStep.from_config(config_dict),
        ]

        doc = await self.paperless.get_document(doc_id)
        all_tags = await self.paperless.get_tags()
        all_correspondents = await self.paperless.get_correspondents()
        all_document_types = await self.paperless.get_document_types()
        all_custom_fields = await self.paperless.get_custom_fields()

        tag_id_to_name = {t["id"]: t["name"] for t in all_tags}
        doc_tag_names = {tag_id_to_name.get(tid, "") for tid in doc.get("tags", [])}

        # Preview simulates ai-process regardless of the document's current tags
        process_tag = config_dict.get("modular_tag_process") or "ai-process"
        preview_trigger_tags = {process_tag}

        from .steps.base import StepContext
        from .llm_handler import LLMHandlerManager

        llm = await LLMHandlerManager.get_handler(for_vision=False)
        ctx = StepContext(
            doc_id=doc_id,
            paperless=self.paperless,
            llm=llm,
            config=config_dict,
            trigger_tags=doc_tag_names,
            ocr_text=doc.get("content", "").strip() if doc.get("content") else "",
        )

        step_records = []
        accumulated_update = {}

        def add_step(
            name: str,
            status: str,
            duration_ms: int,
            error: Optional[str] = None,
            details: Optional[dict[str, Any]] = None,
        ):
            record = {
                "name": name,
                "status": status,
                "duration_ms": duration_ms,
                "error": error,
            }
            if details:
                record["details"] = details
            step_records.append(record)

        for step_instance in steps:
            if not step_instance.can_handle(preview_trigger_tags):
                add_step(step_instance.name, "skipped", 0)
                continue

            step_start = time.time()
            try:
                result = await step_instance.execute(ctx)
                duration_ms = int((time.time() - step_start) * 1000)

                if result.error:
                    add_step(
                        step_instance.name,
                        "failed",
                        duration_ms,
                        result.error,
                        result.details,
                    )
                elif result.skipped:
                    add_step(
                        step_instance.name,
                        "skipped",
                        duration_ms,
                        details=result.details,
                    )
                elif result.data:
                    add_step(
                        step_instance.name,
                        "completed",
                        duration_ms,
                        details=result.details,
                    )
                    accumulated_update.update(result.data)
                else:
                    add_step(
                        step_instance.name,
                        "completed",
                        duration_ms,
                        details=result.details,
                    )
            except Exception as step_error:
                duration_ms = int((time.time() - step_start) * 1000)
                add_step(step_instance.name, "failed", duration_ms, str(step_error))

        proposed = await self._resolve_proposed_changes(
            accumulated_update,
            all_tags,
            all_correspondents,
            all_document_types,
            all_custom_fields,
        )

        end_time = time.time()
        processing_time_ms = int((end_time - start_time) * 1000)

        return {
            "success": True,
            "document_id": doc_id,
            "title": doc.get("title"),
            "updates": accumulated_update,
            "processing_time_ms": processing_time_ms,
            "steps": step_records,
            "proposed_changes": proposed,
        }

    async def _apply_metadata_update(
        self,
        doc_id: int,
        title: str | None,
        correspondent_id: int | None,
        doc_type_id: int | None,
    ) -> None:
        """Apply title, correspondent, and document type updates to Paperless."""
        if not (title or correspondent_id is not None or doc_type_id is not None):
            return
        if title and len(title) > 128:
            title = title[:TITLE_MAX_LENGTH]
        try:
            await self.paperless.update_document(
                doc_id,
                title=title,
                correspondent=correspondent_id,
                document_type=doc_type_id,
            )
        except httpx.HTTPStatusError as e:
            if (
                e.response is None
                or e.response.status_code != 400
                or "does not exist" not in e.response.text
            ):
                raise
            # A referenced correspondent or document type was deleted in Paperless
            # after our metadata cache picked it up. Refresh the cache, drop the
            # stale references, and retry with what is still valid.
            correspondents = await self.paperless.get_correspondents(force_refresh=True)
            doc_types = await self.paperless.get_document_types(force_refresh=True)
            valid_correspondents = {c["id"] for c in correspondents}
            valid_doc_types = {dt["id"] for dt in doc_types}

            dropped = []
            if correspondent_id is not None and correspondent_id not in valid_correspondents:
                dropped.append(f"correspondent {correspondent_id}")
                correspondent_id = None
            if doc_type_id is not None and doc_type_id not in valid_doc_types:
                dropped.append(f"document type {doc_type_id}")
                doc_type_id = None

            if not dropped:
                raise

            logger.warning(
                f"Doc {doc_id}: dropped stale metadata references after cache refresh "
                f"({', '.join(dropped)})"
            )
            if title or correspondent_id is not None or doc_type_id is not None:
                await self.paperless.update_document(
                    doc_id,
                    title=title,
                    correspondent=correspondent_id,
                    document_type=doc_type_id,
                )

    async def _apply_tag_updates(
        self,
        doc_id: int,
        trigger_tags: set[str],
        tag_ids_to_add: list[int],
        tag_ids_to_remove: list[int],
    ) -> None:
        """Replace current document tags: remove trigger tags, add processed tag."""
        doc = await self.paperless.get_document(doc_id)
        current_tag_ids = set(doc.get("tags", []))
        final_tag_ids = (current_tag_ids | set(tag_ids_to_add)) - set(tag_ids_to_remove)
        await self.paperless.update_document(doc_id, tags=list(final_tag_ids))

    def _get_trigger_tag_ids(
        self,
        doc_tag_ids: list[int],
        tag_id_to_name: dict[int, str],
        config_defaults: dict[str, str],
    ) -> list[int]:
        """Return tag IDs on the document that are modular trigger tags."""
        modular_tag_names = {
            config_defaults.get(key) or default
            for key, default in MODULAR_TAG_DEFAULTS.items()
        }
        return [
            tid
            for tid in doc_tag_ids
            if tag_id_to_name.get(tid, "") in modular_tag_names
        ]

    @staticmethod
    def _get_processing_trigger_metadata(
        doc_tag_names: set[str],
        config_dict: dict[str, str],
    ) -> dict[str, Any]:
        """Return the active trigger tags before they are removed from Paperless."""
        candidate_tags = [
            config_dict.get("force_ocr_tag") or "force_ocr",
            config_dict.get("force_ocr_fix_tag") or "force-ocr-fix",
        ]
        for config_key, default in MODULAR_TAG_DEFAULTS.items():
            candidate_tags.append(config_dict.get(config_key) or default)

        process_tag = config_dict.get("process_tag")
        if process_tag:
            candidate_tags.append(process_tag)

        trigger_tags = []
        seen = set()
        for tag in candidate_tags:
            if tag in doc_tag_names and tag not in seen:
                trigger_tags.append(tag)
                seen.add(tag)

        return {
            "trigger_tags": trigger_tags,
            "trigger_mode": trigger_tags[0] if trigger_tags else None,
        }

    async def _process_document_step_based(self, doc_id: int) -> dict[str, Any]:
        start_time = time.time()

        doc = await self.paperless.get_document(doc_id)
        doc_title = doc.get("title", "Untitled")
        logger.info(f"Processing document {doc_id}: {doc_title}")

        metadata = await self._fetch_metadata()
        all_tags = metadata["tags"]
        tag_id_to_name = {t["id"]: t["name"] for t in all_tags}
        doc_tag_names = {tag_id_to_name.get(tid, "") for tid in doc.get("tags", [])}

        step_instances = await self._build_steps()
        config_dict = await self._get_config_dict()

        # The batch list is a snapshot. By the time a document's turn comes its trigger
        # tags may already be gone, and running anyway would write metadata and swap in
        # the processed tag for a document nobody asked about any more.
        if not any(step.can_handle(doc_tag_names) for step in step_instances):
            logger.info(
                "  - Document %s skipped: no trigger tag left to act on", doc_id
            )
            return {
                "success": True,
                "skipped": True,
                "document_id": doc_id,
                "title": doc.get("title"),
                "reason": "no trigger tag left to act on",
            }

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
        trigger_metadata = self._get_processing_trigger_metadata(
            doc_tag_names,
            config_dict,
        )
        try:
            from .scheduler import get_processing_state, mark_document_started

            if get_processing_state().get("is_processing"):
                mark_document_started(
                    doc_id,
                    trigger_tags=trigger_metadata["trigger_tags"],
                    trigger_mode=trigger_metadata["trigger_mode"],
                )
        except Exception as state_error:
            logger.debug("Could not update active document state: %s", state_error)

        from .llm_handler import LLMHandlerManager

        llm = await LLMHandlerManager.get_handler(for_vision=False)

        from .steps.base import StepContext

        ctx = StepContext(
            doc_id=doc_id,
            paperless=self.paperless,
            llm=llm,
            config=config_dict,
            trigger_tags=doc_tag_names,
            ocr_text=doc.get("content", "").strip() if doc.get("content") else "",
        )

        step_records: list[dict] = []
        accumulated_update: dict[str, Any] = {}

        def add_step(
            name: str,
            status: str,
            duration_ms: int,
            error: Optional[str] = None,
            details: Optional[dict[str, Any]] = None,
        ):
            record = {
                "name": name,
                "status": status,
                "duration_ms": duration_ms,
                "error": error,
            }
            if details:
                record["details"] = details
            step_records.append(record)

        try:
            for step_instance in step_instances:
                if not step_instance.can_handle(doc_tag_names):
                    continue

                logger.info(f"  → Step {step_instance.name} for doc {doc_id}")
                try:
                    from .scheduler import update_active_document

                    update_active_document(doc_id, active_step=step_instance.name)
                except Exception as state_error:
                    logger.debug(
                        "Could not update active document step: %s",
                        state_error,
                    )
                step_start = time.time()
                try:
                    result = await step_instance.execute(ctx)
                    duration_ms = int((time.time() - step_start) * 1000)

                    if result.error:
                        add_step(
                            step_instance.name,
                            "failed",
                            duration_ms,
                            result.error,
                            result.details,
                        )
                        logger.info(f"    ✗ {step_instance.name} failed: {result.error}")
                        break
                    elif result.skipped:
                        add_step(
                            step_instance.name,
                            "skipped",
                            duration_ms,
                            details=result.details,
                        )
                        logger.info(
                            f"    - {step_instance.name} skipped ({duration_ms}ms)"
                        )
                    elif result.data:
                        add_step(
                            step_instance.name,
                            "completed",
                            duration_ms,
                            details=result.details,
                        )
                        logger.info(
                            f"    ✓ {step_instance.name} completed ({duration_ms}ms)"
                        )
                        await step_instance.update_metadata(ctx, result)
                        accumulated_update.update(result.data)
                        if "title" in result.data:
                            ctx.ocr_text = ctx.ocr_text or ""
                    else:
                        add_step(
                            step_instance.name,
                            "completed",
                            duration_ms,
                            details=result.details,
                        )
                        logger.info(
                            f"    ✓ {step_instance.name} completed ({duration_ms}ms)"
                        )

                except LLMUnavailableError:
                    # Belongs to the retry handler below. Caught here it would be filed as
                    # a permanent document failure, and a provider that is briefly down
                    # would cost the document its run.
                    raise
                except Exception as step_error:
                    duration_ms = int((time.time() - step_start) * 1000)
                    add_step(step_instance.name, "failed", duration_ms, str(step_error))
                    logger.warning(
                        f"Step {step_instance.name} failed for doc {doc_id}: {step_error}"
                    )
                    break

        except LLMUnavailableError as e:
            await self._delete_log(log_id)
            logger.warning(f"LLM unavailable for doc {doc_id}, will retry: {e}")
            return {
                "success": False,
                "document_id": doc_id,
                "title": doc.get("title"),
                "trigger_tags": trigger_metadata["trigger_tags"],
                "trigger_mode": trigger_metadata["trigger_mode"],
                "error": str(e),
                "retryable": True,
            }

        failed_steps = [step for step in step_records if step["status"] == "failed"]
        if failed_steps:
            error_detail = "; ".join(
                f"{step['name']}: {step.get('error') or 'unknown error'}"
                for step in failed_steps
            )
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "  ✗ Document %s processing FAILED after %sms: %s",
                doc_id,
                processing_time_ms,
                error_detail,
            )
            await self._log_processing(
                doc_id=doc_id,
                doc_title=doc.get("title"),
                status="failed",
                provider=llm.provider,
                model=llm.model,
                llm_response=json.dumps({"steps": step_records}),
                error_message=f"AI processing failed: {error_detail}",
                processing_time_ms=processing_time_ms,
                log_id=log_id,
            )
            return {
                "success": False,
                "document_id": doc_id,
                "title": doc.get("title"),
                "trigger_tags": trigger_metadata["trigger_tags"],
                "trigger_mode": trigger_metadata["trigger_mode"],
                "updates": {},
                "processing_time_ms": processing_time_ms,
                "steps": step_records,
                "proposed_changes": {},
                "error": f"AI processing failed: {error_detail}",
            }

        has_classification = any(
            k in accumulated_update
            for k in ("title", "correspondent", "document_type", "tags")
        )
        process_trigger_name = config_dict.get("modular_tag_process") or "ai-process"
        if process_trigger_name in doc_tag_names and not has_classification:
            async with get_async_session() as session:
                stmt = select(Prompt).where(
                    Prompt.prompt_type == "classify", Prompt.is_active.is_(True)
                )
                classify_prompt = await session.exec(stmt)
                classify_prompt = classify_prompt.first()
                classify_prompt_data = (
                    {
                        "system_prompt": classify_prompt.system_prompt,
                        "user_template": classify_prompt.user_template,
                    }
                    if classify_prompt
                    else None
                )
            if classify_prompt_data:
                try:
                    text = ctx.ocr_text or ""
                    if not text:
                        doc_content = await self.paperless.get_document(doc_id)
                        text = (
                            doc_content.get("content", "").strip()
                            if doc_content.get("content")
                            else ""
                        )
                    user_msg = classify_prompt_data["user_template"].replace(
                        "{content}", text[:10000]
                    )
                    classify_result = await llm.complete(
                        system_prompt=classify_prompt_data["system_prompt"],
                        user_prompt=user_msg,
                        json_mode=False,
                    )
                    raw = classify_result.get("text", "") or classify_result.get(
                        "raw", ""
                    )
                    if raw:
                        parsed = self._parse_classify_response(raw)
                        if parsed.get("correspondent"):
                            corr_id = next(
                                (
                                    c["id"]
                                    for c in metadata["correspondents"]
                                    if c["name"].lower()
                                    == parsed["correspondent"].lower()
                                ),
                                None,
                            )
                            if corr_id:
                                accumulated_update["correspondent"] = corr_id
                        if parsed.get("document_type"):
                            dt_id = next(
                                (
                                    dt["id"]
                                    for dt in metadata["document_types"]
                                    if dt["name"].lower()
                                    == parsed["document_type"].lower()
                                ),
                                None,
                            )
                            if dt_id:
                                accumulated_update["document_type"] = dt_id
                        if parsed.get("tags"):
                            blacklist_raw = config_dict.get("tag_blacklist", "")
                            blacklist = [
                                t.strip().lower()
                                for t in blacklist_raw.split(",")
                                if t.strip()
                            ]
                            tag_ids = [
                                t["id"]
                                for t in metadata["tags"]
                                if t["name"].lower()
                                in [n.lower() for n in parsed["tags"]]
                                and t["name"].lower() not in blacklist
                            ]
                            if tag_ids:
                                accumulated_update["tags"] = tag_ids
                        add_step("classify", "completed", 0)
                except Exception as classify_err:
                    logger.warning(
                        f"Classify fallback failed for doc {doc_id}: {classify_err}"
                    )
                    add_step("classify", "failed", 0, str(classify_err))

        proposed = await self._resolve_proposed_changes(
            accumulated_update,
            all_tags,
            metadata["correspondents"],
            metadata["document_types"],
            metadata["custom_fields"],
        )

        process_tag_name = await self._get_config("process_tag")
        processed_tag_name = await self._get_config("processed_tag")
        tags_by_name = {t["name"]: t["id"] for t in all_tags}
        process_tag_id = (
            tags_by_name.get(process_tag_name) if process_tag_name else None
        )
        processed_tag_id = (
            tags_by_name.get(processed_tag_name) if processed_tag_name else None
        )

        tags_from_steps = accumulated_update.pop("tags", None)

        existing_tag_ids = list(doc.get("tags", []))
        if tags_from_steps is not None:
            existing_tag_ids = list(set(existing_tag_ids) | set(tags_from_steps))

        config_dict = await self._get_config_dict()
        trigger_tag_ids = self._get_trigger_tag_ids(
            doc_tag_ids=doc.get("tags", []),
            tag_id_to_name=tag_id_to_name,
            config_defaults=config_dict,
        )

        title = accumulated_update.pop("title", None)
        correspondent_id = accumulated_update.pop("correspondent", None)
        doc_type_id = accumulated_update.pop("document_type", None)

        try:
            await self._apply_metadata_update(
                doc_id, title, correspondent_id, doc_type_id
            )

            accumulated_update.pop("text", None)
            accumulated_update.pop("content", None)

            if accumulated_update:
                await self.paperless.update_document(doc_id, **accumulated_update)

            # The tag swap is the commit point: it runs only after every value has
            # been accepted by Paperless. If a custom field or date is rejected, the
            # trigger tags stay put and the scheduler picks the document up again.
            tag_ids_to_add = [
                t for t in existing_tag_ids if t not in doc.get("tags", [])
            ]
            tag_ids_to_remove = list(trigger_tag_ids)
            if process_tag_id:
                tag_ids_to_remove.append(process_tag_id)
            if processed_tag_id and processed_tag_id not in existing_tag_ids:
                tag_ids_to_add.append(processed_tag_id)

            if tag_ids_to_add or tag_ids_to_remove:
                await self._apply_tag_updates(
                    doc_id, doc_tag_names, tag_ids_to_add, tag_ids_to_remove
                )
        except Exception as e:
            error_detail = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail = f"{error_detail}: {e.response.text}"
                except Exception:
                    pass
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.info(f"  ✗ Document {doc_id} processing FAILED after {processing_time_ms}ms: {error_detail}")
            await self._log_processing(
                doc_id=doc_id,
                doc_title=doc.get("title"),
                status="failed",
                provider=llm.provider,
                model=llm.model,
                llm_response=json.dumps({"steps": step_records}),
                error_message=f"Paperless update failed: {error_detail}",
                processing_time_ms=processing_time_ms,
                log_id=log_id,
            )
            return {
                "success": False,
                "document_id": doc_id,
                "title": doc.get("title"),
                "trigger_tags": trigger_metadata["trigger_tags"],
                "trigger_mode": trigger_metadata["trigger_mode"],
                "updates": {},
                "processing_time_ms": processing_time_ms,
                "steps": step_records,
                "proposed_changes": proposed,
                "error": f"Paperless update failed: {error_detail}",
            }

        processing_time_ms = int((time.time() - start_time) * 1000)
        logger.info(f"  ✓ Document {doc_id} processing complete ({processing_time_ms}ms)")
        await self._log_processing(
            doc_id=doc_id,
            doc_title=doc.get("title"),
            status="success",
            provider=llm.provider,
            model=llm.model,
            llm_response=json.dumps({"steps": step_records}),
            error_message=None,
            processing_time_ms=processing_time_ms,
            log_id=log_id,
        )

        return {
            "success": True,
            "document_id": doc_id,
            "title": doc.get("title"),
            "trigger_tags": trigger_metadata["trigger_tags"],
            "trigger_mode": trigger_metadata["trigger_mode"],
            "updates": {},
            "processing_time_ms": processing_time_ms,
            "steps": step_records,
            "proposed_changes": proposed,
        }

    @staticmethod
    async def _get_modular_tag_map() -> dict[str, str]:
        """Returns {step_id: tag_name} from config with defaults."""
        step_to_config = {
            "ocr": "modular_tag_ocr",
            "ocr_fix": "modular_tag_ocr_fix",
            "date": "modular_tag_date",
            "title": "modular_tag_title",
            "correspondent": "modular_tag_correspondent",
            "document_type": "modular_tag_document_type",
            "tags": "modular_tag_tags",
            "fields": "modular_tag_fields",
            "process": "modular_tag_process",
        }
        cache = await ConfigCache.get_instance()
        config_dict = await cache.get_all()
        result = {}
        for step_id, config_key in step_to_config.items():
            tag_name = config_dict.get(config_key) or MODULAR_TAG_DEFAULTS.get(
                config_key
            )
            if tag_name:
                result[step_id] = tag_name
        return result

    async def process_tagged_documents(self) -> dict[str, Any]:
        self.paperless.reset_metrics()
        started = time.perf_counter()
        process_tag_name = await self._get_config("process_tag")

        if not process_tag_name:
            return {
                "success": False,
                "error": "Process tag not configured. Please set 'process_tag' in configuration.",
            }

        # Get tags and resolve tag name to ID
        tags = await self.paperless.get_tags()
        tags_by_name = {t["name"]: t["id"] for t in tags}
        process_tag_id = tags_by_name.get(process_tag_name)

        if not process_tag_id:
            return {
                "success": False,
                "error": f"Tag '{process_tag_name}' not found in Paperless",
            }

        documents = await self.paperless.list_documents(tags=[process_tag_id])

        results = []
        for doc in documents:
            result = await self.process_document(doc["id"])
            results.append(result)

        skipped = sum(1 for result in results if result.get("skipped"))
        processed = sum(
            1
            for result in results
            if result.get("success") is True and not result.get("skipped")
        )
        failed = len(results) - processed - skipped
        metrics = self.paperless.get_metrics()
        logger.debug(
            "Legacy process-tag run: processed=%d, requests=%d (paged=%d), duration=%.2fs",
            processed,
            metrics["requests"],
            metrics["paged_requests"],
            time.perf_counter() - started,
        )

        return {
            "success": failed == 0,
            "processed": processed,
            "failed": failed,
            "results": results,
        }
