import logging
from typing import Any

from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)


class CorrespondentStep(AbstractStep):
    name = "correspondent"

    def __init__(self, config):
        self.config = config

    @classmethod
    async def from_config(cls, config):
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        process_tag = self.config.get("modular_tag_process") or "ai-process"
        correspondent_tag = self.config.get("modular_tag_correspondent") or "ai-correspondent"
        return process_tag in tags or correspondent_tag in tags

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
                Prompt.prompt_type == "correspondent", Prompt.is_active == True
            )
            correspondent_prompt = session.exec(stmt).first()
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
            user_msg = prompt_data["user_template"].replace("{content}", text[:10000])
            result = await ctx.llm.complete(
                system_prompt=prompt_data["system_prompt"],
                user_prompt=user_msg,
                json_mode=False,
            )
            corr_text = result.get("text", "").strip() or result.get("raw", "").strip()

            if corr_text and corr_text.lower() != "none":
                correspondents = await ctx.paperless.get_correspondents()
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

