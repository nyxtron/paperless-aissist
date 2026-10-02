"""Document type classification step for the document processing pipeline.

Triggered by ai-process or ai-document-type tag; uses the document_type
prompt to classify the document and set ctx.detected_type for downstream steps.
"""

import logging
from typing import Any, Optional

from ...constants import CONTENT_TRUNCATION_LIMIT
from ...exceptions import LLMError
from .base import AbstractStep, StepContext, StepResult
from .decided import decision_details, decision_enabled, decision_question, decision_threshold, review

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
        text = ctx.ocr_text
        if not text:
            doc = await ctx.paperless.get_document(ctx.doc_id)
            text = doc.get("content", "").strip() if doc.get("content") else ""

        if not text:
            return StepResult(data={}, error="No content available")

        fallback_details = None
        if ctx.decision is not None and decision_enabled(ctx.config, "document_type"):
            try:
                decided, fallback_details = await self._run_decision(ctx, text)
            except LLMError:
                raise
            except Exception as e:
                logger.warning(f"DocumentTypeStep: decision failed for doc {ctx.doc_id}: {e}")
                return StepResult(data={}, error=str(e))
            if decided is not None:
                return decided

        prompt_data = await self._load_prompt()
        if not prompt_data:
            return StepResult(data={}, error=None,
                              details={"decision": fallback_details} if fallback_details else {})

        try:
            result = await self._text_path(ctx, text, prompt_data)
        except LLMError:
            # A provider that is down or refusing fails every document alike.
            # Filed as a step error it looks like a fault of this document, and
            # the run has no way to notice it should stop.
            raise
        except Exception as e:
            logger.warning(f"DocumentTypeStep: failed for doc {ctx.doc_id}: {e}")
            return StepResult(data={}, error=str(e),
                              details={"decision": fallback_details} if fallback_details else {})
        if fallback_details:
            result.details = {**result.details, "decision": fallback_details}
        return result

    @staticmethod
    async def _load_prompt() -> Optional[dict[str, str]]:
        from ...database import get_async_session
        from ...models import Prompt
        from sqlmodel import select

        async with get_async_session() as session:
            stmt = select(Prompt).where(
                Prompt.prompt_type == "document_type", Prompt.is_active.is_(True)
            )
            row = (await session.exec(stmt)).first()
        if row is None:
            return None
        return {"system_prompt": row.system_prompt, "user_template": row.user_template}

    async def _text_path(self, ctx, text, prompt_data) -> StepResult:
        """The text prompt's flow: free-text reply, matched by name."""
        doc_types = await ctx.paperless.get_document_types()
        dt_list = ", ".join(f'"{dt["name"]}"' for dt in doc_types)
        user_msg = (
            prompt_data["user_template"]
            .replace("{content}", text[:CONTENT_TRUNCATION_LIMIT])
            .replace("{document_types_list}", dt_list)
        )
        ctx.note_model(ctx.llm)
        result = await ctx.llm.complete(
            system_prompt=prompt_data["system_prompt"],
            user_prompt=user_msg,
            json_mode=False,
        )
        dt_text = result.get("text", "").strip() or result.get("raw", "").strip()

        if dt_text and dt_text.lower() != "none":
            matched = next(
                (dt for dt in doc_types if dt["name"].lower() == dt_text.lower()),
                None,
            )
            if matched:
                logger.debug(
                    f"DocumentTypeStep: detected {matched['name']} for doc {ctx.doc_id}"
                )
                # Paperless's own spelling, not the model's: the fields step
                # looks up type-specific prompts by this name.
                ctx.detected_type = matched["name"]
                return StepResult(data={"document_type": matched["id"]}, error=None)

        return StepResult(data={}, error=None)

    async def _run_decision(self, ctx, text) -> tuple[Optional[StepResult], Optional[dict]]:
        """The decision branch: (result, None), or (None, details) to fall back."""
        threshold = decision_threshold(ctx.config, "document_type")
        question = decision_question(ctx.config, "document_type")
        doc_types = await ctx.paperless.get_document_types()
        decision = await ctx.decision.decide(
            text[:CONTENT_TRUNCATION_LIMIT], "document_type", [dt["name"] for dt in doc_types],
            question=question, threshold=threshold, ctx=ctx,
        )
        if decision.fallback_reason:
            return None, decision_details(decision, threshold, "fallback")
        if decision.review_reason:
            return review(ctx, "document_type", decision, threshold, decision.review_reason), None
        if decision.index is None:
            reason = "none_of_these" if decision.probability >= threshold else "below_threshold"
            return review(ctx, "document_type", decision, threshold, reason), None
        if decision.probability < threshold:
            return review(ctx, "document_type", decision, threshold, "below_threshold"), None
        matched = doc_types[decision.index]
        # Paperless's own spelling, not the model's: the fields step looks up
        # type-specific prompts by this name.
        ctx.detected_type = matched["name"]
        ctx.decided_fields.add("document_type")
        return StepResult(data={"document_type": matched["id"]},
                          details={"decision": decision_details(decision, threshold, "applied")}), None
