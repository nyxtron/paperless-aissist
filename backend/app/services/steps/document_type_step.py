"""Document type classification step for the document processing pipeline.

Triggered by ai-process or ai-document-type tag; uses the document_type
prompt to classify the document and set ctx.detected_type for downstream steps.
"""

import logging
from typing import Any

from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)


class DocumentTypeStep(AbstractStep):
    """LLM-based document type classification step.

    Triggered by ai-process or ai-document-type tag. Classifies the document
    type, stores the result in ctx.detected_type, and returns result.data["document_type"].
    """

    name = "document_type"

    def __init__(self, config):
        """Initialize with config dict."""
        self.config = config

    @classmethod
    async def from_config(cls, config):
        """Factory: create a DocumentTypeStep from the config dict."""
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        """Return True if ai-process or ai-document-type tag is present."""
        process_tag = self.config.get("modular_tag_process") or "ai-process"
        doc_type_tag = (
            self.config.get("modular_tag_document_type") or "ai-document-type"
        )
        return process_tag in tags or doc_type_tag in tags

    async def execute(self, ctx: StepContext) -> StepResult:
        """Classify the document type from content and available types."""
        from ...database import get_async_session
        from ...models import Prompt
        from sqlmodel import select

        text = ctx.ocr_text
        if not text:
            doc = await ctx.paperless.get_document(ctx.doc_id)
            text = doc.get("content", "").strip() if doc.get("content") else ""

        if not text:
            return StepResult(data={}, error="No content available")

        async with get_async_session() as session:
            stmt = select(Prompt).where(
                Prompt.prompt_type == "document_type", Prompt.is_active.is_(True)
            )
            result = await session.exec(stmt)
            doc_type_prompt = result.first()
            prompt_data = (
                {
                    "system_prompt": doc_type_prompt.system_prompt,
                    "user_template": doc_type_prompt.user_template,
                }
                if doc_type_prompt
                else None
            )

        if not prompt_data:
            return StepResult(data={}, error=None)

        try:
            doc_types = await ctx.paperless.get_document_types()
            dt_list = ", ".join(f'"{dt["name"]}"' for dt in doc_types)
            user_msg = (
                prompt_data["user_template"]
                .replace("{content}", text[:10000])
                .replace("{document_types_list}", dt_list)
            )
            result = await ctx.llm.complete(
                system_prompt=prompt_data["system_prompt"],
                user_prompt=user_msg,
                json_mode=False,
            )
            dt_text = result.get("text", "").strip() or result.get("raw", "").strip()

            if dt_text and dt_text.lower() != "none":
                dt_id = next(
                    (
                        dt["id"]
                        for dt in doc_types
                        if dt["name"].lower() == dt_text.lower()
                    ),
                    None,
                )
                if dt_id:
                    logger.debug(
                        f"DocumentTypeStep: detected {dt_text} for doc {ctx.doc_id}"
                    )
                    ctx.detected_type = dt_text
                    return StepResult(data={"document_type": dt_id}, error=None)

            return StepResult(data={}, error=None)

        except Exception as e:
            logger.warning(f"DocumentTypeStep: failed for doc {ctx.doc_id}: {e}")
            return StepResult(data={}, error=str(e))
