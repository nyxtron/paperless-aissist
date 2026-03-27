import logging
from typing import Any

from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)


class DocumentTypeStep(AbstractStep):
    name = "document_type"

    def __init__(self, config):
        self.config = config

    @classmethod
    async def from_config(cls, config):
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        process_tag = self.config.get("modular_tag_process") or "ai-process"
        doc_type_tag = self.config.get("modular_tag_document_type") or "ai-document-type"
        return process_tag in tags or doc_type_tag in tags

    async def execute(self, ctx: StepContext) -> StepResult:
        from ...database import get_session
        from ...models import Prompt
        from sqlmodel import select

        text = ctx.ocr_text
        if not text:
            doc = await ctx.paperless.get_document(ctx.doc_id)
            text = doc.get("content", "").strip() if doc.get("content") else ""

        if not text:
            return StepResult(data={}, error="No content available")

        with get_session() as session:
            stmt = select(Prompt).where(
                Prompt.prompt_type == "document_type", Prompt.is_active == True
            )
            doc_type_prompt = session.exec(stmt).first()
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
            user_msg = prompt_data["user_template"].replace("{content}", text[:10000])
            result = await ctx.llm.complete(
                system_prompt=prompt_data["system_prompt"],
                user_prompt=user_msg,
                json_mode=False,
            )
            dt_text = result.get("text", "").strip() or result.get("raw", "").strip()

            if dt_text and dt_text.lower() != "none":
                doc_types = await ctx.paperless.get_document_types()
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

