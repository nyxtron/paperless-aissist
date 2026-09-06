"""Correspondent detection step for the document processing pipeline.

Triggered by the ai-process or ai-correspondent tag; uses the correspondent
prompt to match the document against known Paperless correspondents. When
correspondent creation is enabled (opt-in), a proposed name that matches no
existing entry is created — but only when the model produced a trustworthy,
plausible new name, and only through the client's locked get-or-create so
concurrent documents cannot create duplicates.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from ..llm_handler import _extract_json_value
from ..paperless import normalize_name
from ...exceptions import LLMError
from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)

# Names that mean "no sender", not a correspondent to create.
_SENTINEL_NAMES = {
    "none",
    "unknown",
    "n/a",
    "na",
    "null",
    "nil",
    "unbekannt",
    "keine",
    "kein",
}
# A real correspondent name is short. Anything longer is almost always the model
# answering in prose ("Der Absender dieses Dokuments ist ...") rather than naming
# a sender, and must never become a correspondent.
_MAX_NAME_WORDS = 6
_MAX_NAME_LEN = 80


@dataclass
class _Proposal:
    """A correspondent name proposed by the model.

    Attributes:
        name: The proposed name (already stripped).
        is_existing: The model's own claim about whether the name is an existing
            correspondent, or None when it did not say (raw/plain-text replies).
        trusted: True when the name came from a parsed JSON object. False for the
            raw fallback (the model did not emit valid JSON) — a name is then only
            safe to *match* against, never to create from.
    """

    name: str
    is_existing: Optional[bool]
    trusted: bool


class CorrespondentStep(AbstractStep):
    """LLM-based correspondent detection step.

    Triggered by ai-process or ai-correspondent tag. Selects the best matching
    Paperless correspondent from the available list and returns its ID. When the
    correspondent_create_new flag is enabled, a proposed name with no existing
    match is created (via the client's locked get-or-create) instead of dropped.
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

    def _create_enabled(self) -> bool:
        """Return True if opt-in creation of new correspondents is enabled."""
        return (self.config.get("correspondent_create_new") or "false").lower() == "true"

    def _create_owner_mode(self) -> str:
        """Who a created correspondent belongs to: "api_user" (as ever) or "none"."""
        mode = (self.config.get("correspondent_create_owner") or "api_user").lower()
        return "none" if mode == "none" else "api_user"

    def _create_matching_algorithm(self) -> Optional[int]:
        """Paperless matching algorithm for created correspondents, or None to
        leave it to the Paperless default."""
        raw = (self.config.get("correspondent_create_matching") or "").strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
        return value if 0 <= value <= 6 else None

    @staticmethod
    def _parse_response(result: Any) -> Optional[_Proposal]:
        """Extract the proposed correspondent from the LLM response.

        Accepts every shape LLMHandler.complete() can return and pulls a JSON
        object out of plain text when the model wrapped it in prose or fences:
        - a dict already carrying ``name`` (a parsed JSON object);
        - ``{"text": ...}`` (the plain-text reply) whose value is the two-stage
          JSON, JSON embedded in surrounding text, or a bare name (legacy prompt).

        Returns None when nothing usable is found. A name recovered from a
        non-JSON reply is marked ``trusted=False`` so callers never create from it.
        """
        # A dict that itself carries the name is a parsed JSON object (trusted).
        if isinstance(result, dict) and isinstance(result.get("name"), str):
            name = CorrespondentStep._clean_name(result["name"])
            is_existing = CorrespondentStep._coerce_bool(result.get("is_existing"))
            return _Proposal(name, is_existing, True) if name else None

        if isinstance(result, dict):
            raw = (result.get("text") or "").strip() or (result.get("raw") or "").strip()
        elif isinstance(result, str):
            raw = result.strip()
        else:
            raw = ""
        if not raw:
            return None

        parsed = CorrespondentStep._extract_json_object(raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("name"), str):
            name = CorrespondentStep._clean_name(parsed["name"])
            is_existing = CorrespondentStep._coerce_bool(parsed.get("is_existing"))
            return _Proposal(name, is_existing, True) if name else None

        # Not valid JSON: treat the whole reply as a bare name, but untrusted —
        # good enough to match an existing correspondent, never to create one.
        return _Proposal(CorrespondentStep._clean_name(raw), None, False)

    @staticmethod
    def _extract_json_object(text: str) -> Optional[Any]:
        """Parse ``text`` as JSON, or the first balanced JSON object within it.

        Reuses the LLM handler's balanced-brace scanner so a stray brace later in
        the reply can't swallow the object (a greedy ``{.*}`` would).
        """
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            pass
        candidate = _extract_json_value(text)
        if candidate:
            try:
                return json.loads(candidate)
            except (ValueError, TypeError):
                return None
        return None

    @staticmethod
    def _clean_name(name: str) -> str:
        """Strip surrounding whitespace and wrapping quotes from a proposed name.

        The prompt lists candidates in quotes and asks for the exact name, so the
        model sometimes echoes them back quoted. The quotes must be removed from
        the name itself — not just for validation — otherwise the quoted string is
        matched and created verbatim, duplicating the unquoted entry.
        """
        cleaned = name.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
            cleaned = cleaned[1:-1]
        return cleaned.strip().strip("\"'").strip()

    @staticmethod
    def _coerce_bool(value: Any) -> Optional[bool]:
        """Coerce a model-provided is_existing flag to a real tri-state bool.

        Accepts native booleans and the common string spellings; anything else
        (a stray type, or None) is 'unknown' (None), so `is True` cannot be
        walked past by a string like ``"true"``.
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"true", "yes", "1"}:
                return True
            if v in {"false", "no", "0"}:
                return False
        return None

    @staticmethod
    def _is_plausible_new_name(name: str) -> bool:
        """Return True if ``name`` is safe to create as a new correspondent.

        Gates the create branch only (never the lookup): rejects empty and
        sentinel names ("None", "None.", "Unknown", "N/A", …) and prose-length
        replies that are clearly not a sender name.
        """
        stripped = name.strip().strip("\"'").strip()
        if not stripped:
            return False
        sentinel = re.sub(r"[.\s]+$", "", stripped).casefold()
        if sentinel in _SENTINEL_NAMES:
            return False
        if "\n" in stripped or len(stripped) > _MAX_NAME_LEN:
            return False
        if len(stripped.split()) > _MAX_NAME_WORDS:
            return False
        return True

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
            # json_mode stays off: the bundled prompt already asks for JSON and
            # _parse_response extracts it from the reply. Forcing json_mode on
            # would break installs whose (legacy or edited) prompt never gets the
            # new instructions — OpenAI rejects the request and Ollama silently
            # stops matching.
            ctx.note_model(ctx.llm)
            result = await ctx.llm.complete(
                system_prompt=prompt_data["system_prompt"],
                user_prompt=user_msg,
                json_mode=False,
            )
            proposal = self._parse_response(result)

            if proposal is None or not proposal.name:
                return StepResult(data={}, error=None)

            # Reuse an existing correspondent whenever the proposed name matches
            # one (case/whitespace-insensitive), even if the model flagged it as
            # new. This fast path avoids taking the write lock for the common case.
            normalized = normalize_name(proposal.name)
            match = next(
                (c for c in correspondents if normalize_name(c["name"]) == normalized),
                None,
            )
            if match:
                logger.debug(
                    f"CorrespondentStep: detected {match['name']} for doc {ctx.doc_id}"
                )
                return StepResult(data={"correspondent": match["id"]}, error=None)

            # No existing match. Preserve the strict (suggest-only) behavior
            # unless opt-in creation is enabled.
            if not self._create_enabled():
                return StepResult(data={}, error=None)

            # Create gate. Any rejection here is a no-op (the pre-feature
            # behavior), never a step error — a bad correspondent reply must not
            # take the whole document down.
            if not proposal.trusted:
                # Name came from a non-JSON reply; matching it was fine, creating
                # from it is not.
                return StepResult(
                    data={},
                    error=None,
                    skipped=True,
                    details={"correspondent_create_skipped": "untrusted_response"},
                )
            if proposal.is_existing is True:
                # The model claimed this is an existing correspondent but nothing
                # matched — the surest sign it mangled a name. Don't create.
                return StepResult(
                    data={},
                    error=None,
                    skipped=True,
                    details={"correspondent_create_skipped": "claimed_existing_no_match"},
                )
            if not self._is_plausible_new_name(proposal.name):
                return StepResult(
                    data={},
                    error=None,
                    skipped=True,
                    details={"correspondent_create_skipped": "implausible_name"},
                )

            try:
                created, was_created = await ctx.paperless.get_or_create_correspondent(
                    proposal.name,
                    owner_mode=self._create_owner_mode(),
                    matching_algorithm=self._create_matching_algorithm(),
                )
                # Read the id inside the try: a 2xx with an unexpected body would
                # otherwise raise KeyError here and land in the outer handler as a
                # fatal step error — exactly the case the no-op below avoids.
                new_id = created["id"]
                new_name = created.get("name") or proposal.name
            except Exception as create_error:
                # A create failure must not fail the document (which would strip
                # title/type/tags and retry forever): fall back to the no-op the
                # step had before creation existed, recording why for the log.
                logger.warning(
                    f"CorrespondentStep: could not create correspondent "
                    f"'{proposal.name}' for doc {ctx.doc_id}: {create_error}"
                )
                return StepResult(
                    data={},
                    error=None,
                    skipped=True,
                    details={"correspondent_create_failed": str(create_error)},
                )

            if not was_created:
                # A concurrent run created it first; reuse without noise.
                return StepResult(data={"correspondent": new_id}, error=None)

            logger.info(
                f"CorrespondentStep: created correspondent '{new_name}' "
                f"(id={new_id}) for doc {ctx.doc_id}"
            )
            return StepResult(
                data={"correspondent": new_id},
                error=None,
                details={
                    "created_correspondent": {
                        "id": new_id,
                        "name": new_name,
                    }
                },
            )

        except LLMError:
            # A provider that is down or refusing fails every document alike.
            # Filed as a step error it looks like a fault of this document, and
            # the run has no way to notice it should stop.
            raise
        except Exception as e:
            logger.warning(f"CorrespondentStep: failed for doc {ctx.doc_id}: {e}")
            return StepResult(data={}, error=str(e))
