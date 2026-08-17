"""Date detection step for the document processing pipeline."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlmodel import select

from ...constants import CONTENT_TRUNCATION_LIMIT
from ...database import get_async_session
from ...models import Prompt
from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DATE_KEYS = ("created_date", "confidence", "evidence")


def _date_payload(response: Any) -> dict[str, Any] | None:
    """Pull the date object out of a reply, or None if there isn't one.

    JSON mode hands over the parsed object directly. A reply the parser could
    not make sense of arrives as {"raw": ...}, and text mode wraps it in
    {"text": ...} — both may still hold the object as a string, so they get one
    more attempt before the step gives up.
    """
    if not isinstance(response, dict):
        return None
    if any(key in response for key in DATE_KEYS):
        return response
    wrapped = response.get("text") or response.get("raw")
    if not isinstance(wrapped, str):
        return None
    try:
        parsed = json.loads(wrapped.strip())
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


class DateStep(AbstractStep):
    """Detect the original document date when the date modular tag is present."""

    name = "date"

    def __init__(self, config: dict[str, str]):
        self.config = config
        self.date_tag = (config.get("modular_tag_date") or "ai-date") if config else "ai-date"

    @classmethod
    async def from_config(cls, config: dict[str, str]) -> "DateStep":
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        return self.date_tag in tags

    async def execute(self, ctx: StepContext) -> StepResult:
        doc = await ctx.paperless.get_document(ctx.doc_id)
        text = (ctx.ocr_text or "").strip()
        if not text:
            text = doc.get("content", "").strip() if doc.get("content") else ""
        original_title = doc.get("title", "")
        current_created = doc.get("created", "")
        current_date = datetime.now(timezone.utc).date().isoformat()

        if not text:
            return StepResult(
                details={
                    "created_date": None,
                    "confidence": "low",
                    "evidence": "",
                    "reason": "no content",
                },
                skipped=True,
            )

        async with get_async_session() as session:
            stmt = select(Prompt).where(
                Prompt.prompt_type == "date",
                Prompt.is_active.is_(True),
            )
            result = await session.exec(stmt)
            prompt = result.first()

        if not prompt:
            return StepResult(
                details={
                    "created_date": None,
                    "confidence": "low",
                    "evidence": "",
                    "reason": "no active date prompt",
                },
                skipped=True,
            )

        user_msg = (
            prompt.user_template.replace("{content}", text[:CONTENT_TRUNCATION_LIMIT])
            .replace("{title}", original_title or "")
            .replace("{created_date}", current_created or "")
            .replace("{current_date}", current_date)
        )

        # Deliberately not wrapped in try/except: an unreachable provider has to reach the
        # processor's retry handler instead of being filed as a bad date reply.
        response = await ctx.llm.complete(
            system_prompt=prompt.system_prompt,
            user_prompt=user_msg,
            json_mode=True,
        )
        payload = _date_payload(response)
        if payload is None:
            return StepResult(error="invalid date response: reply carried no date fields")

        created_date = payload.get("created_date")
        confidence = str(payload.get("confidence") or "low").lower()
        evidence = str(payload.get("evidence") or "").strip()
        details: dict[str, Any] = {
            "created_date": created_date,
            "confidence": confidence,
            "evidence": evidence,
        }

        if created_date is None:
            details["reason"] = "no reliable document date"
            return StepResult(details=details, skipped=True)

        if confidence == "low":
            details["reason"] = "low confidence"
            return StepResult(details=details, skipped=True)

        if confidence not in {"high", "medium"}:
            details["reason"] = f"unsupported confidence: {confidence}"
            return StepResult(details=details, skipped=True)

        if not isinstance(created_date, str) or not ISO_DATE_RE.match(created_date):
            details["reason"] = "invalid date format"
            return StepResult(
                details=details,
                skipped=True,
            )

        try:
            date.fromisoformat(created_date)
        except ValueError:
            details["reason"] = "invalid calendar date"
            return StepResult(
                details=details,
                skipped=True,
            )

        return StepResult(data={"created_date": created_date}, details=details)
