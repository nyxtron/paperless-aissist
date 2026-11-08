"""Closed-list decisions with a probability per answer.

The options get letters, the model answers one token, and the letters'
probabilities say how sure it was. Lists longer than an adapter can take are
split into chunks plus "None of these", with a final round among the chunk
winners. The rules below are the ones the 60-document measurement used, plus
the two safety rules agreed afterwards: the winner's probability is the
lowest it had in any round, and a round that barely answered with letters
sends the field to review.
"""

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Sequence

from ..llm_handler import LLMHandler
from .adapters import Adapter, DecisionSkipped, DecisionUnsupported, RoundResult
from .formats import NONE_DESCRIPTION, NONE_LABEL, text_digest

logger = logging.getLogger(__name__)

REVIEW_REASONS = (
    "below_threshold", "low_mass", "final_none", "creation_off", "none_of_these",
    "named_existing", "no_name_prompt", "no_name", "untrusted_response",
    "claimed_existing_no_match", "implausible_name", "create_failed",
)
FALLBACK_REASONS = (
    "no_logprobs", "unsupported_parameter", "route_missing", "format_unsupported",
    "provider_unsupported", "url_missing", "model_missing", "prompt_inactive",
    "empty_list", "no_letters", "context_exceeded",
)
DEFAULT_QUESTIONS = {
    "correspondent": "Who sent this document (the correspondent)?",
    "document_type": "What type of document is this?",
}
MIN_LETTER_MASS = 0.5
# A provider that cannot do this is not asked again right away.
UNSUPPORTED_RECHECK_SECONDS = 600
# Nor is Ollama, when it did not say what a model can do.
CAPABILITIES_RETRY_SECONDS = 60


def chunks(seq: Sequence, per_chunk: int) -> list[list]:
    """Even chunks of at most per_chunk: 112 → 19,19,19,19,19,17; 30 → 15,15."""
    items = list(seq)
    if len(items) <= per_chunk:
        return [items]
    count = math.ceil(len(items) / per_chunk)
    size = math.ceil(len(items) / count)
    return [items[i : i + size] for i in range(0, len(items), size)]


@dataclass
class Decision:
    method: str
    provider: str
    model: str
    index: Optional[int] = None
    choice: Optional[str] = None
    probability: Optional[float] = None
    mass: Optional[float] = None
    top: list[dict[str, Any]] = field(default_factory=list)
    requests: int = 0
    review_reason: Optional[str] = None
    fallback_reason: Optional[str] = None
    fallback_detail: Optional[str] = None
    rendered: Optional[str] = None
    full: Optional[str] = None
    text_chars: int = 0
    text_sha256: str = ""


PromptLoader = Callable[[str], Awaitable[Optional[dict[str, str]]]]


class DecisionService:
    def __init__(
        self,
        handler: LLMHandler,
        adapter_cls: Optional[type[Adapter]],
        fallback_reason: Optional[str],
        prompt_loader: Optional[PromptLoader],
        *,
        ask_capabilities: bool = False,
    ):
        self._handler = handler
        self._adapter_cls = adapter_cls
        self._fallback_reason = fallback_reason
        self._prompt_loader = prompt_loader
        # Under auto an Ollama model is asked once what it can do, when the
        # first document needs it; until Ollama answers, it is asked again
        # every minute.
        self._ask_capabilities = ask_capabilities
        self._capabilities_retry_at: Optional[float] = None
        self._unsupported_until: Optional[float] = None
        self._unsupported: tuple[Optional[str], Optional[str]] = (None, None)
        self._adapter_calls: list[Adapter] = []

    @classmethod
    async def from_config(cls) -> "DecisionService":
        """Build the service from the settings; empty fields mean the main LLM."""
        from .adapters import OllamaLettersAdapter, pick_adapter

        own_provider = await _config("llm_provider_decision")
        fmt = await _config("decision_format") or "auto"
        handler = await LLMHandler.from_config(role="decision")
        fallback = None
        if own_provider and not handler.api_base:
            fallback = "url_missing"
        elif not handler.model:
            fallback = "model_missing"
        adapter_cls, reason = pick_adapter(handler.provider, handler.model, fmt)
        # Only a model name tells Nimble apart; a decision model like clef-flash
        # is known by what Ollama says it can do.
        ask = fmt == "auto" and adapter_cls is OllamaLettersAdapter and not fallback
        return cls(handler, adapter_cls, fallback or reason, _load_decision_prompt, ask_capabilities=ask)

    @property
    def provider(self) -> str:
        return self._handler.provider

    @property
    def model(self) -> str:
        return self._handler.model

    @property
    def method(self) -> str:
        return self._adapter_cls.method if self._adapter_cls else "text"

    @property
    def is_closed(self) -> bool:
        return self._handler.is_closed

    async def retire(self) -> None:
        await self._handler.retire()

    async def close(self) -> None:
        await self._handler.close()

    def _fallback(
        self, reason: str, detail: Optional[str], requests: int = 0, method: str = "text",
        digest: Optional[dict[str, Any]] = None,
    ) -> Decision:
        return Decision(method, self.provider, self.model, requests=requests,
                        fallback_reason=reason, fallback_detail=detail, **(digest or {}))

    def _remembered_unsupported(self) -> Optional[tuple[str, Optional[str]]]:
        if self._unsupported_until is None:
            return None
        if time.monotonic() >= self._unsupported_until:
            self._unsupported_until = None
            return None
        return self._unsupported  # type: ignore[return-value]

    def forget_unsupported(self) -> None:
        self._unsupported_until = None

    async def _settle_route(self) -> None:
        """Under auto, send an Ollama decision model to /v1/systemone."""
        if not self._ask_capabilities:
            return
        if self._capabilities_retry_at is not None and time.monotonic() < self._capabilities_retry_at:
            return
        from .adapters import pick_adapter

        capabilities = await self._handler.ollama_capabilities()
        if capabilities is None:
            self._capabilities_retry_at = time.monotonic() + CAPABILITIES_RETRY_SECONDS
            return
        self._ask_capabilities = False
        adapter_cls, _ = pick_adapter(self.provider, self.model, "auto", capabilities)
        if adapter_cls is not self._adapter_cls:
            self._adapter_cls = adapter_cls
            # A refusal remembered from the letters route says nothing about this one.
            self.forget_unsupported()

    async def probe(self) -> Decision:
        """The settings page's test: a fresh two-option question."""
        self.forget_unsupported()
        self._capabilities_retry_at = None
        question = (await _config("decision_question_correspondent") or "").strip() or DEFAULT_QUESTIONS["correspondent"]
        return await self.decide(PROBE_TEXT, "correspondent", PROBE_OPTIONS, question=question, threshold=0.9)

    async def decide(
        self,
        text: str,
        field: str,
        options: Sequence[str],
        *,
        question: str,
        threshold: float,
        ctx: Any = None,
    ) -> Decision:
        """Pick one of options for the document text, or say why not."""
        if self._fallback_reason:
            return self._fallback(self._fallback_reason, None)
        await self._settle_route()
        remembered = self._remembered_unsupported()
        if remembered:
            return self._fallback(*remembered)
        if not options:
            return self._fallback("empty_list", None)
        prompt = None
        if self._adapter_cls.uses_prompt:
            prompt = await self._prompt_loader(field) if self._prompt_loader else None
            if prompt is None:
                return self._fallback("prompt_inactive", None)

        adapter = self._adapter_cls(self._handler, prompt)
        # The last adapter only; a cached service would grow with every field.
        self._adapter_calls = [adapter]
        labels = [str(o) for o in options]
        descriptions = {NONE_LABEL: NONE_DESCRIPTION}
        per_chunk = adapter.max_options - 1
        preview = bool(getattr(ctx, "preview", False))
        noted = False

        async def run(rounds: list[tuple[str, list[int]]]) -> list[RoundResult]:
            nonlocal noted
            if ctx is not None and not noted:
                ctx.note_model(self)
                noted = True
            asks = [(name, [labels[i] for i in idxs] + [NONE_LABEL]) for name, idxs in rounds]
            results = await adapter.score_rounds(text, question, asks, descriptions)
            for r in results:
                if not r.probs:
                    raise DecisionSkipped("no_letters", None)
            return results

        def low(r: RoundResult) -> bool:
            return r.mass is not None and r.mass < MIN_LETTER_MASS

        def finish(index, choice, p, r: RoundResult, review=None) -> Decision:
            # The adapter that answered: under auto the route can change while
            # another document's decision is still running.
            return Decision(
                adapter.method, self.provider, self.model, index=index, choice=choice,
                probability=p, mass=r.mass, top=self._top(r, r_names[id(r)]),
                requests=adapter.requests, review_reason=review, rendered=r.rendered,
                full=r.full if preview else None, **digest,
            )

        # The option names each result was asked about, by result identity, so
        # the top-3 can be named without carrying the lists around.
        r_names: dict[int, list[str]] = {}

        async def run_named(rounds):
            results = await run(rounds)
            for (name, idxs), r in zip(rounds, results):
                r_names[id(r)] = [labels[i] for i in idxs] + [NONE_LABEL]
            return results

        # Once anything is sent, the stored request names the text it was for.
        digest = text_digest(text)
        try:
            first = [(f"c{i}", idxs) for i, idxs in enumerate(chunks(range(len(labels)), per_chunk))]
            results = await run_named(first)
            winners: list[tuple[int, float, bool]] = []  # global index, p so far, low mass so far
            winner_results: list[RoundResult] = []
            nones: list[tuple[float, bool, RoundResult]] = []
            for (name, idxs), r in zip(first, results):
                none_local = len(idxs)
                top_local = max(r.probs, key=r.probs.get)
                if top_local == none_local:
                    nones.append((r.probs[none_local], low(r), r))
                else:
                    winners.append((idxs[top_local], r.probs[top_local], low(r)))
                    winner_results.append(r)
            if not winners:
                p, _, r = min(nones, key=lambda t: t[0])
                review = "low_mass" if any(l for _, l, _ in nones) else None
                return finish(None, NONE_LABEL, p, r, review)
            if len(winners) == 1:
                idx, p, is_low = winners[0]
                return finish(idx, labels[idx], p, winner_results[0], "low_mass" if is_low else None)

            current = winners
            while len(current) > per_chunk:
                parts = chunks(current, per_chunk)
                rounds = [(f"c{i}", [c[0] for c in part]) for i, part in enumerate(parts)]
                results = await run_named(rounds)
                nxt = []
                for part, (name, idxs), r in zip(parts, rounds, results):
                    none_local = len(idxs)
                    top_local = max(r.probs, key=r.probs.get)
                    if top_local == none_local:
                        return finish(None, NONE_LABEL, r.probs[none_local], r, "final_none")
                    idx, p_prev, low_prev = part[top_local]
                    nxt.append((idx, min(p_prev, r.probs[top_local]), low_prev or low(r)))
                current = nxt

            final_idxs = [c[0] for c in current]
            (r,) = await run_named([("final", final_idxs)])
            none_local = len(final_idxs)
            top_local = max(r.probs, key=r.probs.get)
            if top_local == none_local:
                return finish(None, NONE_LABEL, r.probs[none_local], r, "final_none")
            idx, p_prev, low_prev = current[top_local]
            p = min(p_prev, r.probs[top_local])
            return finish(idx, labels[idx], p, r, "low_mass" if (low_prev or low(r)) else None)
        except DecisionUnsupported as e:
            # A refusal from a route auto has left since says nothing about the current one.
            if type(adapter) is self._adapter_cls:
                self._unsupported = (e.reason, e.detail)
                self._unsupported_until = time.monotonic() + UNSUPPORTED_RECHECK_SECONDS
            return self._fallback(e.reason, e.detail, adapter.requests, adapter.method, digest=digest)
        except DecisionSkipped as e:
            return self._fallback(e.reason, e.detail, adapter.requests, adapter.method, digest=digest)

    @staticmethod
    def _top(r: RoundResult, names: list[str]) -> list[dict[str, Any]]:
        ranked = sorted(r.probs.items(), key=lambda kv: -kv[1])[:3]
        return [{"name": names[i], "p": p} for i, p in ranked]


PROBE_TEXT = "Rechnung der Stadtwerke Saarbrücken über Strom für März"
PROBE_OPTIONS = ["Stadtwerke Saarbrücken", "Telekom"]


async def _load_decision_prompt(field: str) -> Optional[dict[str, str]]:
    """The active letter prompt for a field, or None when it is off or missing."""
    from sqlmodel import select

    from ...database import get_async_session
    from ...models import Prompt

    async with get_async_session() as session:
        stmt = select(Prompt).where(
            Prompt.prompt_type == f"decision_{field}", Prompt.is_active.is_(True)
        )
        row = (await session.exec(stmt)).first()
    if row is None:
        return None
    return {"system_prompt": row.system_prompt, "user_template": row.user_template}


async def _config(key: str) -> str:
    from ..config_cache import ConfigCache

    return await (await ConfigCache.get_instance()).get(key)


class DecisionServiceManager:
    """One cached service, dropped whenever a setting it was built from changes."""

    _service: Optional[DecisionService] = None
    _lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def get_service(cls) -> DecisionService:
        """Return the cached service, building one from the settings if needed."""
        service = cls._service
        if service is not None and not service.is_closed:
            return service
        async with cls._lock:
            service = cls._service
            if service is not None and not service.is_closed:
                return service
            service = await DecisionService.from_config()
            old = cls._service
            cls._service = service
            if old is not None:
                try:
                    await old.close()
                except Exception:
                    pass
            return service

    @classmethod
    async def reset(cls):
        """Drop the service; a document already deciding finishes on the old one."""
        async with cls._lock:
            service = cls._service
            if service is not None:
                cls._service = None
                try:
                    await service.retire()
                except Exception:
                    pass

    @classmethod
    async def close(cls):
        """Close the cached service and clear it."""
        async with cls._lock:
            if cls._service is not None:
                try:
                    await cls._service.close()
                except Exception:
                    pass
                cls._service = None
