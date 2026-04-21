"""Correspondent detection step for the document processing pipeline.

Triggered by the ai-process or ai-correspondent tag; uses the correspondent
prompt to match the document against known Paperless correspondents.
"""

import logging
from typing import Any

from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)


class CorrespondentStep(AbstractStep):
    """LLM-based correspondent detection step.

    Triggered by ai-process or ai-correspondent tag. Selects the best matching
    Paperless correspondent from the available list and returns its ID.
    """

    name = "correspondent"

    def __init__(self, config):
        """Initialize with config dict."""
        self.config = config

    @classmethod
    async def from_config(cls, config):
        """Factory: create a CorrespondentStep from the config dict."""
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        """Return True if ai-process or ai-correspondent tag is present."""
        process_tag = self.config.get("modular_tag_process") or "ai-process"
        correspondent_tag = (
            self.config.get("modular_tag_correspondent") or "ai-correspondent"
        )
        return process_tag in tags or correspondent_tag in tags

    async def execute(self, ctx: StepContext) -> StepResult:
        """Detect the correspondent from content and available list."""
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
                Prompt.prompt_type == "correspondent", Prompt.is_active.is_(True)
            )
            result = await session.exec(stmt)
            correspondent_prompt = result.first()
            prompt_data = (
                {
                    "system_prompt": correspondent_prompt.system_prompt,
                    "user_template": correspondent_prompt.user_template,
                }
                if correspondent_prompt
                else None
            )

        if not prompt_data:
            return StepResult(data={}, error=None)

        try:
            correspondents = await ctx.paperless.get_correspondents()
            corr_list = ", ".join(f'"{c["name"]}"' for c in correspondents)
            user_msg = (
                prompt_data["user_template"]
                .replace("{content}", text[:10000])
                .replace("{correspondents_list}", corr_list)
            )
            result = await ctx.llm.complete(
                system_prompt=prompt_data["system_prompt"],
                user_prompt=user_msg,
                json_mode=False,
            )
            corr_text = result.get("text", "").strip() or result.get("raw", "").strip()

            if corr_text and corr_text.lower() != "none":
                corr_id = next(
                    (
                        c["id"]
                        for c in correspondents
                        if c["name"].lower() == corr_text.lower()
                    ),
                    None,
                )
                if corr_id:
                    logger.debug(
                        f"CorrespondentStep: detected {corr_text} for doc {ctx.doc_id}"
                    )
                    return StepResult(data={"correspondent": corr_id}, error=None)

            return StepResult(data={}, error=None)

        except Exception as e:
            logger.warning(f"CorrespondentStep: failed for doc {ctx.doc_id}: {e}")
            return StepResult(data={}, error=str(e))
