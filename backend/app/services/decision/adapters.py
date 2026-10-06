"""One adapter per route to a model, and the letter parser they share.

An adapter builds the request, sends it through LLMHandler.post_json and
hands back a probability per option. The concrete adapters are below the
base class; the service only knows the base.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, NoReturn, Optional

from ...exceptions import LLMHttpError
from ..llm_handler import LLMHandler
from .formats import (
    LETTERS,
    TEXT_PLACEHOLDER,
    go_json,
    nimble_user_message,
    render_letter_prompt,
    systemone_questions,
    unique_keys,
)


TOP_LOGPROBS = 20


class DecisionUnsupported(Exception):
    """The provider cannot do this at all; the service remembers it for a while."""

    def __init__(self, reason: str, detail: Optional[str] = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class DecisionSkipped(Exception):
    """This field of this document could not be decided; the next one may be."""

    def __init__(self, reason: str, detail: Optional[str] = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass
class RoundResult:
    probs: dict[int, float] = field(default_factory=dict)
    mass: Optional[float] = None
    rendered: str = ""
    full: str = ""
    input_tokens: Optional[int] = None


def letter_probs(top: list[dict[str, Any]], n: int) -> tuple[dict[int, float], float]:
    """Probabilities over the option letters among the top candidates.

    Whitespace around a token is stripped, only an exact uppercase option
    letter counts, and the first occurrence wins ("B" and " B" are not added
    up). An entry without a number is no candidate. The mass is how much of
    the model's answer sat on letters at all.
    """
    found: dict[int, float] = {}
    for entry in top:
        token = str(entry.get("token", "")).strip()
        if len(token) != 1 or token not in LETTERS[:n]:
            continue
        index = LETTERS.index(token)
        logprob = entry.get("logprob")
        if index not in found and isinstance(logprob, (int, float)):
            found[index] = float(logprob)
    if not found:
        return {}, 0.0
    best = max(found.values())
    z = sum(math.exp(v - best) for v in found.values())
    probs = {i: math.exp(v - best) / z for i, v in found.items()}
    mass = sum(math.exp(v) for v in found.values())
    return probs, mass


class Adapter:
    method: str = ""
    max_options: int = TOP_LOGPROBS
    uses_prompt: bool = True

    def __init__(self, handler: LLMHandler, prompt: Optional[dict[str, str]] = None):
        self.handler = handler
        self.prompt = prompt
        self.requests = 0

    async def score_rounds(
        self,
        text: str,
        question: str,
        asks: list[tuple[str, list[str]]],
        descriptions: Mapping[str, str],
    ) -> list[RoundResult]:
        """Score every round, one request after another so the prompt cache
        can reuse the document text. A round without any letter ends the
        tournament right there."""
        results = []
        for name, labels in asks:
            result = await self._score_one(text, question, name, labels, descriptions)
            if not result.probs:
                raise DecisionSkipped("no_letters", None)
            results.append(result)
        return results

    async def _score_one(
        self,
        text: str,
        question: str,
        name: str,
        labels: list[str],
        descriptions: Mapping[str, str],
    ) -> RoundResult:
        raise NotImplementedError


# A 400/422 naming one of these refused something the decision adds to the
# request, so this route cannot score letters at all.
_UNSUPPORTED_PARAMETER = ("logprob", "top_logprobs", "max_tokens", "temperature",
                          "unsupported parameter", "unsupported_parameter", "unsupported_value",
                          "unknown field")


def classify_http_error(error: LLMHttpError, *, systemone: bool = True) -> Optional[tuple[str, bool]]:
    """(reason, provider-level) for a refusal the decision can live with, or None.

    Provider-level means no document will get further on this route; the rest
    only hit this document. None leaves the error a provider failure. Only the
    SystemOne route can be missing; a plain 404 on /api/chat is a wrong URL.
    """
    body = (error.body or "").lower()
    status = error.status_code
    # Ollama's wording changed in 0.35: "exceeds the available context size".
    too_long = "input is never truncated" in body or "exceeds the available context size" in body
    if status == 413 or (status == 400 and too_long):
        return "context_exceeded", False
    if status == 400 and "not supported by system one" in body:
        return "format_unsupported", True
    # A decision model such as clef-flash only answers on /v1/systemone.
    if status == 400 and ("does not support chat" in body or "does not support generate" in body):
        return "format_unsupported", True
    if status == 404 and "no endpoints found" in body:
        return "no_logprobs", True
    # Ollama's own "model not found" is a JSON 404; only a missing route is plain text.
    if systemone and status == 404 and body.strip().startswith("404 page not found"):
        return "route_missing", True
    if status in (400, 422) and any(mark in body for mark in _UNSUPPORTED_PARAMETER):
        return "unsupported_parameter", True
    return None


def _raise_classified(error: LLMHttpError, *, systemone: bool = True) -> NoReturn:
    verdict = classify_http_error(error, systemone=systemone)
    if verdict is None:
        raise error
    reason, provider_level = verdict
    detail = (error.body or "")[:300]
    if provider_level:
        raise DecisionUnsupported(reason, detail)
    raise DecisionSkipped(reason, detail)


def _placeholder(text: str) -> str:
    return TEXT_PLACEHOLDER.format(chars=len(text))


def _plain_placeholder(rendered: str, placeholder: str) -> str:
    """go_json escapes the placeholder's < and >; show it as the letter prompts do."""
    return rendered.replace(go_json(placeholder)[1:-1], placeholder)


def _ollama_options(handler: LLMHandler) -> dict[str, Any]:
    options: dict[str, Any] = {"temperature": 0, "num_predict": 1}
    if handler.num_ctx is not None:
        options["num_ctx"] = handler.num_ctx
    return options


def _ollama_top(data: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        top = data["logprobs"][0]["top_logprobs"]
    except (KeyError, IndexError, TypeError):
        top = None
    if not top:
        raise DecisionUnsupported("no_logprobs", "answer carried no logprobs")
    return top


def _openai_top(data: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        top = data["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
    except (KeyError, IndexError, TypeError):
        top = None
    if not top:
        raise DecisionUnsupported("no_logprobs", "answer carried no logprobs")
    return top


def _transcript(messages: list[dict[str, str]]) -> str:
    return "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages)


class _LettersAdapter(Adapter):
    """The letter prompt from the prompt table, for any instruct model."""

    def _messages(self, text: str, question: str, labels: list[str]) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.prompt["system_prompt"]},
            {"role": "user", "content": render_letter_prompt(self.prompt["user_template"], text, question, labels)},
        ]

    def _render(self, text: str, question: str, labels: list[str]) -> tuple[str, str]:
        """The request with the text replaced, and in full."""
        shown = self._messages(_placeholder(text), question, labels)
        return _transcript(shown), _transcript(self._messages(text, question, labels))


class OllamaLettersAdapter(_LettersAdapter):
    method = "ollama_letters"

    async def _score_one(self, text, question, name, labels, descriptions) -> RoundResult:
        messages = self._messages(text, question, labels)
        payload = {
            "model": self.handler.model, "messages": messages, "stream": False, "think": False,
            "logprobs": True, "top_logprobs": TOP_LOGPROBS, "options": _ollama_options(self.handler),
        }
        self.requests += 1
        try:
            data = await self.handler.post_json(
                "/api/chat", payload, prompt_parts=(messages[0]["content"], messages[1]["content"])
            )
        except LLMHttpError as e:
            _raise_classified(e, systemone=False)
        probs, mass = letter_probs(_ollama_top(data), len(labels))
        rendered, full = self._render(text, question, labels)
        return RoundResult(probs, mass, rendered, full, data.get("prompt_eval_count"))


class OpenAILettersAdapter(_LettersAdapter):
    method = "openai_letters"

    async def _score_one(self, text, question, name, labels, descriptions) -> RoundResult:
        messages = self._messages(text, question, labels)
        payload: dict[str, Any] = {
            "model": self.handler.model, "messages": messages, "temperature": 0,
            "max_tokens": 1, "logprobs": True, "top_logprobs": TOP_LOGPROBS,
        }
        if self.handler.provider == "openrouter":
            # Otherwise OpenRouter may route to an endpoint that drops logprobs.
            payload["provider"] = {"require_parameters": True}
        self.requests += 1
        try:
            data = await self.handler.post_json("/chat/completions", payload)
        except LLMHttpError as e:
            _raise_classified(e, systemone=False)
        probs, mass = letter_probs(_openai_top(data), len(labels))
        rendered, full = self._render(text, question, labels)
        usage = data.get("usage") or {}
        return RoundResult(probs, mass, rendered, full, usage.get("prompt_tokens"))


class OllamaNimbleAdapter(Adapter):
    """Nimble's own format over /api/chat; Ollama adds the model's system prompt."""

    method = "ollama_nimble"
    uses_prompt = False

    async def _score_one(self, text, question, name, labels, descriptions) -> RoundResult:
        content = nimble_user_message(text, question, labels, descriptions)
        payload = {
            "model": self.handler.model, "messages": [{"role": "user", "content": content}],
            "stream": False, "think": False, "logprobs": True, "top_logprobs": TOP_LOGPROBS,
            "options": _ollama_options(self.handler),
        }
        self.requests += 1
        try:
            data = await self.handler.post_json("/api/chat", payload, prompt_parts=("", content))
        except LLMHttpError as e:
            _raise_classified(e, systemone=False)
        probs, mass = letter_probs(_ollama_top(data), len(labels))
        placeholder = _placeholder(text)
        shown = _plain_placeholder(
            nimble_user_message(placeholder, question, labels, descriptions), placeholder
        )
        return RoundResult(probs, mass, shown, content, data.get("prompt_eval_count"))


class OllamaSystemOneAdapter(Adapter):
    """Ollama's decision route, one question per request."""

    method = "ollama_systemone"
    uses_prompt = False
    max_options = 26

    async def score_rounds(self, text, question, asks, descriptions) -> list[RoundResult]:
        # Several questions in one body let the other chunks' options colour
        # each answer, so every chunk is asked on its own.
        results = []
        for ask in asks:
            results += await self._send(text, question, [ask], descriptions)
        return results

    def _payload(self, text, question, asks, descriptions) -> dict[str, Any]:
        return {"model": self.handler.model, "state": text,
                "questions": systemone_questions(question, asks, descriptions)}

    async def _send(self, text, question, asks, descriptions) -> list[RoundResult]:
        payload = self._payload(text, question, asks, descriptions)
        self.requests += 1
        try:
            data = await self.handler.post_json("/v1/systemone", payload, prompt_parts=("", text))
        except LLMHttpError as e:
            _raise_classified(e)
        answers = data.get("answers") or {}
        usage = data.get("usage") or {}
        placeholder = _placeholder(text)
        shown = _plain_placeholder(go_json({**payload, "state": placeholder}), placeholder)
        full = go_json(payload)
        results = []
        for name, labels in asks:
            raw = (answers.get(name) or {}).get("probabilities")
            if not isinstance(raw, dict):
                raise DecisionUnsupported("no_logprobs", "answer carried no probabilities")
            # Options are keyed by text, so duplicates map back by position.
            probs = {i: float(raw[key]) for i, key in enumerate(unique_keys(labels)) if key in raw}
            results.append(RoundResult(probs, None, shown, full, usage.get("input_tokens")))
        return results


def pick_adapter(
    provider: str, model: str, fmt: str, capabilities: Optional[list[str]] = None
) -> tuple[Optional[type[Adapter]], Optional[str]]:
    """The adapter for a provider and format, or why there is none.

    capabilities is what Ollama's /api/show says the model can do; under auto
    a decision model goes to its own route.
    """
    fmt = fmt or "auto"
    if provider == "grok":
        return None, ("provider_unsupported" if fmt in ("auto", "letters") else "format_unsupported")
    if provider == "ollama":
        if fmt == "nimble" or (fmt == "auto" and "nimble" in (model or "").lower()):
            return OllamaNimbleAdapter, None
        if fmt == "systemone" or (fmt == "auto" and "decision" in (capabilities or ())):
            return OllamaSystemOneAdapter, None
        return OllamaLettersAdapter, None
    if fmt in ("nimble", "systemone"):
        return None, "format_unsupported"
    return OpenAILettersAdapter, None
