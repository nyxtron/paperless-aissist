import logging
from typing import Any

from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)


class OCRFixStep(AbstractStep):
    name = "ocr_fix"

    def __init__(self, config):
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
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        return self.force_ocr_fix_tag in tags or self.force_ocr_tag in tags

    async def execute(self, ctx: StepContext) -> StepResult:
        from ...database import get_session
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

        ocr_fix_prompt = None
        with get_session() as session:
            stmt = select(Prompt).where(
                Prompt.prompt_type == "ocr_fix", Prompt.is_active == True
            )
            ocr_fix_prompt = session.exec(stmt).first()

        if not ocr_fix_prompt:
            return StepResult(data={}, error=None)

        try:
            fix_result = await ctx.llm.complete(
                system_prompt=ocr_fix_prompt.system_prompt,
                user_prompt=ocr_fix_prompt.user_template.replace("{content}", text[:10000]),
                json_mode=False,
            )
            fixed_text = (
                fix_result.get("text", "").strip() or fix_result.get("raw", "").strip()
            )

            if fixed_text:
                ctx.ocr_text = fixed_text
                logger.debug(f"OCRFixStep: fixed text for doc {ctx.doc_id}")
                return StepResult(data={"text": fixed_text}, error=None)

            return StepResult(data={}, error=None)

        except Exception as e:
            logger.warning(f"OCRFixStep: failed for doc {ctx.doc_id}: {e}")
            return StepResult(data={}, error=str(e))

    async def update_metadata(self, ctx: StepContext, result: StepResult) -> None:
        if result.data.get("text"):
            await ctx.paperless.update_document(ctx.doc_id, content=result.data["text"])

    @staticmethod
    async def _get_config(config: dict, key: str, default: str = None) -> str:
        return config.get(key) if config else default
