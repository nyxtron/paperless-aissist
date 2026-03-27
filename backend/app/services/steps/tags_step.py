import logging
from typing import Any

from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)


class TagsStep(AbstractStep):
    name = "tags"

    def __init__(self, config):
        self.config = config

    @classmethod
    async def from_config(cls, config):
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        process_tag = self.config.get("modular_tag_process") or "ai-process"
        tags_tag = self.config.get("modular_tag_tags") or "ai-tags"
        return process_tag in tags or tags_tag in tags

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
                Prompt.prompt_type == "tag", Prompt.is_active == True
            )
            tag_prompt = session.exec(stmt).first()
            prompt_data = (
                {
                    "system_prompt": tag_prompt.system_prompt,
                    "user_template": tag_prompt.user_template,
                }
                if tag_prompt
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
            tag_text = result.get("text", "").strip() or result.get("raw", "").strip()

            if tag_text and tag_text.lower() != "none":
                blacklist_raw = await self._get_config(self.config, "tag_blacklist", "")
                blacklist = [
                    t.strip().lower() for t in blacklist_raw.split(",") if t.strip()
                ]

                tag_names = [t.strip() for t in tag_text.split(",") if t.strip()]
                all_tags = await ctx.paperless.get_tags()
                tag_ids = []

                for tag_name in tag_names:
                    if blacklist and tag_name.lower() in blacklist:
                        continue
                    tag_id = next(
                        (
                            t["id"]
                            for t in all_tags
                            if t["name"].lower() == tag_name.lower()
                        ),
                        None,
                    )
                    if tag_id:
                        tag_ids.append(tag_id)

                if tag_ids:
                    logger.debug(
                        f"TagsStep: assigned {len(tag_ids)} tags to doc {ctx.doc_id}"
                    )
                    return StepResult(data={"tags": tag_ids}, error=None)

            return StepResult(data={}, error=None)

        except Exception as e:
            logger.warning(f"TagsStep: failed for doc {ctx.doc_id}: {e}")
            return StepResult(data={}, error=str(e))

    async def update_metadata(self, ctx: StepContext, result: StepResult) -> None:
        pass

    @staticmethod
    async def _get_config(config: dict, key: str, default: str = None) -> str:
        return config.get(key) if config else default
