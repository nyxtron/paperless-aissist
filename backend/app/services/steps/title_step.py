"""Title generation step for the document processing pipeline.

Triggered by the ai-process or ai-title tag; uses the title prompt template
to generate a document title via the LLM.
"""

import logging
from typing import Any

from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)


class TitleStep(AbstractStep):
    """LLM-based title generation step.

    Triggered by ai-process or ai-title tag. Generates a concise document title
    using the title prompt template and populates result.data["title"].
    """

    name = "title"

    def __init__(self, config):
        """Initialize with config dict."""
        self.config = config

    @classmethod
    async def from_config(cls, config):
        """Factory: create a TitleStep from the config dict."""
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        """Return True if ai-process or ai-title tag is present."""
        process_tag = self.config.get("modular_tag_process") or "ai-process"
        title_tag = self.config.get("modular_tag_title") or "ai-title"
        return process_tag in tags or title_tag in tags

    async def execute(self, ctx: StepContext) -> StepResult:
        """Generate a title from the document content and return it."""
        from ...database import get_async_session
        from ...constants import CONTENT_TRUNCATION_LIMIT
        from ...models import Prompt
        from sqlmodel import select

        doc = await ctx.paperless.get_document(ctx.doc_id)
        text = ctx.ocr_text or (
            doc.get("content", "").strip() if doc.get("content") else ""
        )
        original_title = doc.get("title", "")

        if not text:
            return StepResult(data={}, error="No content available")

        async with get_async_session() as session:
            stmt = select(Prompt).where(
                Prompt.prompt_type == "title", Prompt.is_active.is_(True)
            )
            result = await session.exec(stmt)
            title_prompt = result.first()
            title_prompt_data = (
                {
                    "system_prompt": title_prompt.system_prompt,
                    "user_template": title_prompt.user_template,
                }
                if title_prompt
                else None
            )

        if not title_prompt_data:
            return StepResult(data={}, error=None)

        try:
            correspondents = await ctx.paperless.get_correspondents()
            corr_list = ", ".join(f'"{c["name"]}"' for c in correspondents)
            user_msg = (
                title_prompt_data["user_template"]
                .replace("{content}", text[:CONTENT_TRUNCATION_LIMIT])
                .replace("{title}", original_title)
                .replace("{correspondents_list}", corr_list)
            )
            result = await ctx.llm.complete(
                system_prompt=title_prompt_data["system_prompt"],
                user_prompt=user_msg,
                json_mode=False,
            )
            title_text = result.get("text", "").strip() or result.get("raw", "").strip()

            if title_text:
                logger.debug(f"TitleStep: generated title for doc {ctx.doc_id}")
                return StepResult(data={"title": title_text}, error=None)

            return StepResult(data={}, error=None)

        except Exception as e:
            logger.warning(f"TitleStep: failed for doc {ctx.doc_id}: {e}")
            return StepResult(data={}, error=str(e))
