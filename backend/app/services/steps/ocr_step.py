"""OCR extraction step for the document processing pipeline.

Triggered by the force_ocr tag; extracts text from PDFs using the vision LLM
and stores the result as the document's content.
"""

import logging
from typing import Any

from .base import AbstractStep, StepContext, StepResult
from ..vision import VisionPipeline

logger = logging.getLogger(__name__)


class OCRStep(AbstractStep):
    """Vision-based OCR extraction step.

    Triggered by the force_ocr tag. Extracts text from PDFs using VisionPipeline
    and updates ctx.ocr_text and the document content.
    """

    name = "ocr"

    def __init__(self, config):
        """Initialize with config dict; reads tag names for trigger and override."""
        self.config = config
        self.force_ocr_tag = (
            config.get("force_ocr_tag", "force_ocr") if config else "force_ocr"
        )
        self.force_ocr_fix_tag = (
            config.get("force_ocr_fix_tag", "force-ocr-fix")
            if config
            else "force-ocr-fix"
        )

    @classmethod
    async def from_config(cls, config):
        """Factory: create an OCRStep from the config dict."""
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        """Return True if the force_ocr tag is present."""
        return self.force_ocr_tag in tags

    async def execute(self, ctx: StepContext) -> StepResult:
        """Run vision OCR on the document PDF and update ctx.ocr_text."""
        from ...database import get_async_session
        from ...models import Prompt
        from sqlmodel import select

        enable_vision = await self._get_config(self.config, "enable_vision", "false")
        if enable_vision != "true":
            return StepResult(data={}, error=None)

        try:
            vision_pipeline = await VisionPipeline.create()
            pdf_bytes = await ctx.paperless.get_document_file(ctx.doc_id)

            vision_prompt_text = None
            async with get_async_session() as session:
                stmt = select(Prompt).where(
                    Prompt.prompt_type == "vision_ocr", Prompt.is_active.is_(True)
                )
                result = await session.exec(stmt)
                vp = result.first()
                if vp:
                    vision_prompt_text = vp.system_prompt

            vision_result = await vision_pipeline.extract_text_from_pdf(
                pdf_bytes, prompt=vision_prompt_text
            )
            text = vision_result.get("text", "") or vision_result.get("raw", "")

            ctx.ocr_text = text
            logger.debug(f"OCRStep: extracted {len(text)} chars for doc {ctx.doc_id}")

            return StepResult(data={"text": text}, error=None)

        except Exception as e:
            logger.warning(f"OCRStep: vision OCR failed for doc {ctx.doc_id}: {e}")
            return StepResult(data={}, error=str(e))

    async def update_metadata(self, ctx: StepContext, result: StepResult) -> None:
        if result.data.get("text"):
            await ctx.paperless.update_document(ctx.doc_id, content=result.data["text"])

    @staticmethod
    async def _get_config(config: dict, key: str, default: str = None) -> str:
        """Helper to read a config key with a default."""
        return config.get(key) if config else default
