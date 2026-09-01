"""OCR fix/refinement step for the document processing pipeline.

Triggered by ai-ocr-fix, force_ocr_fix, or force_ocr tags; applies an LLM pass
to correct OCR errors in the existing ctx.ocr_text.
"""

import logging
import os
from typing import Any

from ...exceptions import LLMError
from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)

DEFAULT_OCR_FIX_MAX_CHARS = 10000

# An OCR correction keeps the text roughly intact. A much shorter reply means the
# model summarized or stopped early, so the result is discarded instead of
# overwriting the document.
MIN_RESULT_LENGTH_RATIO = 0.8


class OCRFixStep(AbstractStep):
    """LLM-based OCR post-processing step.

    Triggered by ai-ocr-fix, force_ocr_fix, or force_ocr tags. Rewrites
    ctx.ocr_text to fix recognition errors using the ocr_fix prompt template.
    """

    name = "ocr_fix"

    def __init__(self, config):
        """Initialize with config dict."""
        self.config = config
        self.force_ocr_tag = (
            config.get("force_ocr_tag", "force_ocr") if config else "force_ocr"
        )
        self.force_ocr_fix_tag = (
            config.get("force_ocr_fix_tag", "force-ocr-fix")
            if config
            else "force-ocr-fix"
        )
        self.ocr_fix_tag = (
            (config.get("modular_tag_ocr_fix") or "ai-ocr-fix")
            if config
            else "ai-ocr-fix"
        )
        self.ocr_fix_max_chars = self._parse_max_chars(config)

    @classmethod
    async def from_config(cls, config):
        """Factory: create an OCRFixStep from the config dict."""
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        """Return True if an OCR-fix trigger tag is present."""
        return (
            self.ocr_fix_tag in tags
            or self.force_ocr_fix_tag in tags
            or self.force_ocr_tag in tags
        )

    async def execute(self, ctx: StepContext) -> StepResult:
        """Apply OCR fix LLM pass to ctx.ocr_text and update the document content."""
        from ...database import get_async_session
        from ...models import Prompt
        from sqlmodel import select

        ocr_fix_enabled = await self._get_config(
            self.config, "ocr_post_process", "true"
        )
        if ocr_fix_enabled != "true":
            return StepResult(data={}, error=None)

        text = ctx.ocr_text
        if not text:
            return StepResult(data={}, error=None)

        content_length = len(text)
        if content_length > self.ocr_fix_max_chars:
            logger.info(
                "OCRFixStep: skipping doc %s because content length %d exceeds max %d",
                ctx.doc_id,
                content_length,
                self.ocr_fix_max_chars,
            )
            return StepResult(
                data={},
                error=None,
                details={
                    "reason": "content_too_large",
                    "content_length": content_length,
                    "max_chars": self.ocr_fix_max_chars,
                },
                skipped=True,
            )

        ocr_fix_prompt = None
        async with get_async_session() as session:
            stmt = select(Prompt).where(
                Prompt.prompt_type == "ocr_fix", Prompt.is_active.is_(True)
            )
            result = await session.exec(stmt)
            ocr_fix_prompt = result.first()

        if not ocr_fix_prompt:
            return StepResult(data={}, error=None)

        try:
            fix_result = await ctx.llm.complete(
                system_prompt=ocr_fix_prompt.system_prompt,
                user_prompt=ocr_fix_prompt.user_template.replace(
                    "{content}", text[: self.ocr_fix_max_chars]
                ),
                json_mode=False,
            )
            fixed_text = (
                fix_result.get("text", "").strip() or fix_result.get("raw", "").strip()
            )

            if fixed_text:
                # The corrected text replaces the whole document content, so a reply
                # that is much shorter than the original is a summary or a truncated
                # generation — writing it back would destroy document text.
                if len(fixed_text) < len(text) * MIN_RESULT_LENGTH_RATIO:
                    logger.warning(
                        "OCRFixStep: discarding result for doc %s — %d chars returned "
                        "for %d chars of input, keeping the original text",
                        ctx.doc_id,
                        len(fixed_text),
                        len(text),
                    )
                    return StepResult(
                        data={},
                        error=None,
                        details={
                            "reason": "result_too_short",
                            "original_length": len(text),
                            "result_length": len(fixed_text),
                        },
                        skipped=True,
                    )

                ctx.ocr_text = fixed_text
                logger.debug(f"OCRFixStep: fixed text for doc {ctx.doc_id}")
                return StepResult(data={"text": fixed_text}, error=None)

            return StepResult(data={}, error=None)
        except LLMError:
            # A provider that is down or refusing fails every document alike.
            # Filed as a step error it looks like a fault of this document, and
            # the run has no way to notice it should stop.
            raise
        except Exception as e:
            logger.warning(f"OCRFixStep: failed for doc {ctx.doc_id}: {e}")
            return StepResult(data={}, error=str(e))

    async def update_metadata(self, ctx: StepContext, result: StepResult) -> None:
        if result.data.get("text"):
            await ctx.paperless.update_document(ctx.doc_id, content=result.data["text"])

    @staticmethod
    async def _get_config(config: dict, key: str, default: str = None) -> str:
        """Helper to read a config key with a default."""
        return config.get(key) if config else default

    @staticmethod
    def _parse_max_chars(config: dict | None) -> int:
        value = config.get("ocr_fix_max_chars") if config else None
        if not value:
            value = os.environ.get("OCR_FIX_MAX_CHARS", str(DEFAULT_OCR_FIX_MAX_CHARS))
        try:
            max_chars = int(value)
        except (TypeError, ValueError):
            return DEFAULT_OCR_FIX_MAX_CHARS
        if max_chars < 1:
            return DEFAULT_OCR_FIX_MAX_CHARS
        return max_chars
