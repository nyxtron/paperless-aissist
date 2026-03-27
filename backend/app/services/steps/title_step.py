import logging
from typing import Any

from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)


class TitleStep(AbstractStep):
    name = "title"

    def __init__(self, config):
        self.config = config

    @classmethod
    async def from_config(cls, config):
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        process_tag = self.config.get("modular_tag_process") or "ai-process"
        title_tag = self.config.get("modular_tag_title") or "ai-title"
        return process_tag in tags or title_tag in tags

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
                Prompt.prompt_type == "title", Prompt.is_active == True
            )
            title_prompt = session.exec(stmt).first()
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
            user_msg = title_prompt_data["user_template"].replace(
                "{content}", text[:10000]
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

