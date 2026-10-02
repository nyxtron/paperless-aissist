"""LLM client supporting Ollama and OpenAI-compatible APIs (including Grok).

Provides text completion (with optional JSON mode) and vision multimodal
completion. LLMHandler instances are managed by the singleton LLMHandlerManager.
"""

import asyncio
import contextvars
import logging
import json
import re
import time
import httpx
from typing import Any, Callable, Iterator, Optional
from ..exceptions import LLMError, LLMHttpError, LLMUnavailableError

logger = logging.getLogger(__name__)


_WHITESPACE_RE = re.compile(r"\s+")
# A run of one mark: dot leaders, form lines, separators.
_REPEATED_MARK_RE = re.compile(r"([^\w\s]|_)\1+")
_OPENERS = {"}": "{", "]": "["}

# Filled while a step runs (see processor.py): every prompt Ollama had to cut
# to fit its context window during that step, so the step can report it.
PROMPT_CUTS: contextvars.ContextVar[Optional[list[dict[str, Any]]]] = (
    contextvars.ContextVar("prompt_cuts", default=None)
)

# No text takes fewer tokens than one per five characters once runs of
# whitespace and of one mark are folded (German prose sits near 3.8, English
# near 4.3, a separator line up to 40 before folding), so fewer evaluated
# tokens than that means part of the prompt was dropped.
_MAX_CHARS_PER_TOKEN = 5.0
# Tokens Ollama keeps from the start of a prompt it has to cut.
_OLLAMA_NUM_KEEP = 4
# No Ollama default window is below 2,048, so a cut prompt keeps at least ~1,026.
_MIN_CUT_TOKENS = 1000
_WINDOW_RECHECK_SECONDS = 600
# A lookup that found nothing is tried again sooner: the model may just have
# been swapped out.
_WINDOW_RETRY_SECONDS = 60
_WINDOW_LOOKUP_TIMEOUT = 5.0


def _prompt_was_cut(
    prompt_chars: int, evaluated: Optional[int], window: Optional[int]
) -> bool:
    """Whether Ollama evaluated only part of the prompt.

    The response never says so; Ollama only logs a warning on its own side and
    carries on. Recent versions keep the first few tokens and the tail, cut to
    about half the window, so the system prompt and the option lists are the
    first to go. Older versions filled the window with the tail instead.
    """
    if not evaluated:
        return False
    if window:
        # Ollama cuts to one of these sizes, so any other count means it fit.
        return (
            evaluated >= window - 1
            or evaluated == window - (window - _OLLAMA_NUM_KEEP) // 2
        )
    return prompt_chars > evaluated * _MAX_CHARS_PER_TOKEN


def _prompt_chars(*parts: str) -> int:
    """Characters the check above compares, with runs folded."""
    return sum(
        len(_REPEATED_MARK_RE.sub(r"\1", _WHITESPACE_RE.sub(" ", part)))
        for part in parts
    )


def _iter_json_candidates(text: str) -> Iterator[str]:
    """Yield every balanced JSON object/array in text, in the order they appear.

    One pass, honoring quoted strings and escapes so braces inside string values
    neither open nor close a candidate. A value cut off mid-object is never
    completed and therefore never yielded.
    """
    stack: list[str] = []
    start = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            if stack:
                in_string = True
        elif ch in "{[":
            if not stack:
                start = i
            stack.append(ch)
        elif ch in _OPENERS:
            if not stack:
                continue
            if stack[-1] != _OPENERS[ch]:
                stack.clear()
                continue
            stack.pop()
            if not stack:
                yield text[start : i + 1]


def _rank_json_candidate(value: Any) -> int:
    """Rate how much a parsed value resembles an answer rather than commentary.

    Every prompt asks for an object or a list of objects, so those rank highest
    and an empty list ranks just below — the extract prompt uses it for "nothing
    found". A bracketed number in prose ("see entry [3]") parses cleanly but can
    never be an answer, so it scores zero and is passed over.
    """
    if isinstance(value, dict):
        return 2
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            return 2
        if not value:
            return 1
    return 0


def _extract_json_value(text: str, prompt: str = "") -> Optional[str]:
    """Return the JSON value in text most likely to be the model's own answer.

    Models restate the format they were asked for, so a reply can hold both our
    example and the real answer. Position cannot tell them apart — some models
    quote the example first, others append it afterwards as a "this is the shape
    I followed" note — but the example is ours, so pass ``prompt`` and a value
    repeated from it verbatim gives way to one that is not. It only ever gives
    way: a reply holding nothing else is the answer, however much it reads like
    the example, and our prompts print the answers for the empty cases in full.

    Of what remains the best-shaped value wins, ties going to the last, so a
    bracketed aside like "see entry [3]" cannot displace a real answer.
    """
    if not isinstance(text, str):
        return None
    echoed = _WHITESPACE_RE.sub("", prompt) if prompt else ""
    best: Optional[tuple[int, str]] = None
    best_including_quotes: Optional[tuple[int, str]] = None
    for candidate in _iter_json_candidates(text):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        rank = _rank_json_candidate(value)
        if not rank:
            continue
        if best_including_quotes is None or rank >= best_including_quotes[0]:
            best_including_quotes = (rank, candidate)
        if value and echoed and _WHITESPACE_RE.sub("", candidate) in echoed:
            continue
        if best is None or rank >= best[0]:
            best = (rank, candidate)
    # Quoting only decides between an example and an answer standing side by side.
    # When it would leave nothing at all the reply simply matches what we asked for,
    # which is what a well-behaved model does — the date prompt spells out its own
    # "no date found" object, and dropping that would fail the document instead.
    chosen = best or best_including_quotes
    return chosen[1] if chosen else None


def _loads_llm_json(content: str, prompt: str = "") -> Any:
    """Parse JSON from an LLM response, tolerating code fences and stray prose.

    Some models wrap their JSON in a ```json ... ``` fence (or prepend a word)
    even in JSON mode. Try a direct parse first, then recover the value that
    reads like the answer. Pass the prompt that produced the reply so an example
    quoted back from it is not mistaken for one. Falls back to {"raw": content}
    so callers keep the old contract.
    """
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass
    candidate = _extract_json_value(content, prompt)
    if candidate is not None:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            pass
    return {"raw": content}


# Worth another run. Any other status means the request itself was refused, and
# sending it again unchanged would only be refused again.
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def _llm_error_for(error: httpx.HTTPError, message: str) -> LLMError:
    """Pick the exception that says whether this failure is worth retrying.

    A provider that is unreachable or rate-limiting gets another run. A refused
    key, an unknown model or a rejected parameter does not: the processor drops
    its log entry before retrying, so filing those as transient would loop the
    document every scheduler pass and leave no record of why.
    """
    response = getattr(error, "response", None)
    if response is not None and response.status_code not in RETRYABLE_STATUS:
        return LLMError(message)
    return LLMUnavailableError(message)


# What a model is told to reply with for a page carrying no text. Asking it to
# stay silent does not work — a model trained to answer will describe the empty
# page instead — so it gets something permitted to say and we drop it here.
NO_TEXT_MARKER = "NO_TEXT"


def _drop_no_text_marker(content: str) -> str:
    """Turn the marker for a blank page into no text at all."""
    if content.strip().rstrip(".").strip().upper() == NO_TEXT_MARKER:
        return ""
    return content


# A reply that ends for any of these reasons is incomplete, whatever text came with
# it. A page that is simply blank always ends with "stop", so these never fire on the
# back of a duplex scan — measured against Ollama and the OpenAI-compatible servers.
TRUNCATED_FINISH_REASONS = frozenset({"length", "content_filter"})


def _incomplete_reason(data: dict) -> Optional[str]:
    """Name the reason a reply was cut short, or None if it ran to the end.

    Only positively bad values count. An absent field means the server does not
    report one, and treating that as a failure would break models that leave it
    out entirely.
    """
    reason = data.get("done_reason")
    if reason is None:
        choices = data.get("choices") or [{}]
        reason = choices[0].get("finish_reason") if isinstance(choices[0], dict) else None
    if isinstance(reason, str) and reason in TRUNCATED_FINISH_REASONS:
        return reason
    return None


def _http_error_detail(error: httpx.HTTPError) -> str:
    """Describe an httpx error including the server's own explanation.

    str() on a status error names only the code and URL, so the sentence that
    says what the server actually objected to gets dropped — which is exactly
    the part needed to tell a rejected parameter from an unreachable host.
    """
    detail = str(error)
    response = getattr(error, "response", None)
    if response is None:
        return detail
    body = (response.text or "").strip()
    return f"{detail} - {body[:500]}" if body else detail


OPENAI_COMPATIBLE_PROVIDERS = frozenset({"openai", "grok", "openrouter"})
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_REFERER = "https://github.com/nyxtron/paperless-aissist"
OPENROUTER_TITLE = "Paperless-AIssist"
DEFAULT_TEMPERATURE = 0.3
PROMPT_CONTROL_CHARS_TO_REMOVE = dict.fromkeys(
    list(range(0x00, 0x09))
    + list(range(0x0B, 0x0D))
    + list(range(0x0E, 0x20))
    + [0x7F]
)


def sanitize_prompt_text(text: str) -> str:
    """Strip control characters that can break LLM chat endpoints."""
    return text.translate(PROMPT_CONTROL_CHARS_TO_REMOVE)


def _report_page(
    on_page: Optional[Callable[[int, int], None]], page: int, pages: int
) -> None:
    """Tell the caller which page is going out, without ever failing the read."""
    if on_page is None:
        return
    try:
        on_page(page, pages)
    except Exception as e:
        logger.debug("Page progress callback failed: %s", e)


class LLMHandler:
    """HTTP client for LLM inference via Ollama or OpenAI-compatible APIs.

    Attributes:
        provider: "ollama", "openai", "grok", or "openrouter".
        model: Model name passed to the API.
        api_base: Base URL for the API endpoint.
        api_key: Optional API key for authenticated endpoints.
        timeout: Request timeout in seconds.
        temperature: Default sampling temperature for requests.
        max_tokens: Optional default output token limit.
        num_ctx: Optional Ollama context window size.
    """

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "llama3",
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 600.0,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        num_ctx: Optional[int] = None,
    ):
        self.provider = provider
        self.model = model
        self.api_base = api_base or ""
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.num_ctx = num_ctx
        self._client: Optional[httpx.AsyncClient] = None
        # Ollama's own window for this model when num_ctx is not set, read from
        # /api/ps and refreshed now and then.
        self._server_window: Optional[int] = None
        self._server_window_read_at: Optional[float] = None
        self._closed = False
        # Requests still running, so a replaced handler can finish them first.
        self._in_flight = 0
        self._retired = False

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            if self.provider == "openrouter":
                headers["HTTP-Referer"] = OPENROUTER_REFERER
                headers["X-OpenRouter-Title"] = OPENROUTER_TITLE
            self._client = httpx.AsyncClient(
                base_url=self.api_base,
                timeout=self.timeout,
                headers=headers,
            )
        return self._client

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def close(self):
        """Close the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._closed = True

    async def retire(self):
        """Close once the requests still running on this handler are done."""
        self._retired = True
        if not self._in_flight:
            await self.close()

    async def _after_request(self):
        self._in_flight -= 1
        if self._retired and not self._in_flight:
            try:
                await self.close()
            except Exception as e:
                # The answer is already here and worth more than a clean close.
                logger.debug("Could not close a replaced LLM client: %s", e)

    async def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        prompt_parts: Optional[tuple[str, str]] = None,
    ) -> dict[str, Any]:
        """POST a JSON body and return the JSON answer.

        A refusal keeps its status and body (LLMHttpError), a provider that is
        down stays retryable, and a prompt Ollama cut is noted like in
        complete(). The finish reason is left alone: a one-token answer always
        ends with "length".
        """
        self._in_flight += 1
        try:
            try:
                response = await self.client.post(path, json=payload)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                detail = _http_error_detail(e)
                if e.response.status_code in RETRYABLE_STATUS:
                    raise LLMUnavailableError(f"{self.provider} request failed: {detail}")
                raise LLMHttpError(
                    f"{self.provider} request failed: {detail}",
                    status_code=e.response.status_code,
                    body=e.response.text or "",
                )
            except httpx.HTTPError as e:
                raise _llm_error_for(e, f"{self.provider} request failed: {_http_error_detail(e)}")
            data = response.json()
            if prompt_parts is not None and self.provider == "ollama":
                evaluated = data.get("prompt_eval_count") or (data.get("usage") or {}).get(
                    "input_tokens"
                )
                # /v1/systemone ignores options.num_ctx; only the server's window counts there.
                window = None if path == "/v1/systemone" else self.num_ctx
                await self._note_if_cut(prompt_parts[0], prompt_parts[1], evaluated, window)
            return data
        finally:
            await self._after_request()

    @classmethod
    async def from_config(
        cls, for_vision: bool = False, role: Optional[str] = None
    ) -> "LLMHandler":
        """Construct a LLMHandler from the application config.

        Args:
            for_vision: If True, use the vision-specific config keys (_vision suffix).
            role: "decision" reads the llm_*_decision keys (see _decision_from_config).

        Returns:
            A configured LLMHandler instance.
        """
        if role == "decision":
            return await cls._decision_from_config()
        suffix = "_vision" if for_vision else ""
        provider = await cls._get_config(f"llm_provider{suffix}")
        model = await cls._get_config(f"llm_model{suffix}")
        api_base = await cls._get_config(f"llm_api_base{suffix}")
        api_key = await cls._get_config(f"llm_api_key{suffix}")

        if for_vision:
            # Fall back to main LLM settings for connection/provider if not set
            if not provider:
                provider = await cls._get_config("llm_provider")
            if not api_base:
                api_base = await cls._get_config("llm_api_base")
            if not api_key:
                api_key = await cls._get_config("llm_api_key")

        if not provider:
            provider = "ollama"
        if not model:
            if provider == "openrouter":
                model = "openai/gpt-4o" if for_vision else "openai/gpt-4o-mini"
            else:
                model = "llama3" if not for_vision else "llava"
        if provider == "openrouter" and not api_base:
            api_base = OPENROUTER_API_BASE

        timeout_str = await cls._get_config(f"llm_timeout{suffix}")
        if for_vision and not timeout_str:
            timeout_str = await cls._get_config("llm_timeout")
        timeout = float(timeout_str) if timeout_str else 600.0

        temperature_str = await cls._get_config(f"llm_temperature{suffix}")
        if for_vision and not temperature_str:
            temperature_str = await cls._get_config("llm_temperature")
        temperature = cls._parse_temperature(temperature_str)

        max_tokens_str = await cls._get_config(f"llm_max_tokens{suffix}")
        if for_vision and not max_tokens_str:
            max_tokens_str = await cls._get_config("llm_max_tokens")
        max_tokens = cls._parse_max_tokens(max_tokens_str)

        num_ctx_str = await cls._get_config(f"llm_num_ctx{suffix}")
        if for_vision and not num_ctx_str:
            num_ctx_str = await cls._get_config("llm_num_ctx")
        num_ctx = cls._parse_positive_int(num_ctx_str)

        logger.info(f"Provider: {provider}, Model: {model}, API Base: {api_base}")

        return cls(
            provider=provider,
            model=model,
            api_base=api_base,
            api_key=api_key,
            timeout=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
            num_ctx=num_ctx,
        )

    @classmethod
    async def _decision_from_config(cls) -> "LLMHandler":
        """The handler for the decision model.

        With no provider of its own the connection is the main LLM's as a
        group, and a stored decision URL or key is ignored; only the model may
        differ. With its own provider nothing is inherited, so a key never
        goes to a host it was not meant for. An empty URL or model stays
        empty: the decision service turns that into a fallback, not a request.
        """
        own_provider = await cls._get_config("llm_provider_decision")
        model = await cls._get_config("llm_model_decision")
        if own_provider:
            provider = own_provider
            api_base = await cls._get_config("llm_api_base_decision")
            api_key = await cls._get_config("llm_api_key_decision") or None
        else:
            provider = await cls._get_config("llm_provider") or "ollama"
            api_base = await cls._get_config("llm_api_base")
            api_key = await cls._get_config("llm_api_key") or None
            if not model:
                model = await cls._get_config("llm_model") or (
                    "openai/gpt-4o-mini" if provider == "openrouter" else "llama3"
                )
        if provider == "openrouter" and not api_base:
            api_base = OPENROUTER_API_BASE
        timeout_str = (
            await cls._get_config("llm_timeout_decision")
            or await cls._get_config("llm_timeout")
        )
        num_ctx_str = (
            await cls._get_config("llm_num_ctx_decision")
            or await cls._get_config("llm_num_ctx")
        )
        logger.info(
            f"Decision provider: {provider}, model: {model or '(none)'}, API base: {api_base}"
        )
        return cls(
            provider=provider,
            model=model or "",
            api_base=api_base,
            api_key=api_key,
            timeout=float(timeout_str) if timeout_str else 600.0,
            num_ctx=cls._parse_positive_int(num_ctx_str),
        )

    @staticmethod
    async def _get_config(key: str) -> Optional[str]:
        from .config_cache import ConfigCache

        cache = await ConfigCache.get_instance()
        return await cache.get(key)

    @staticmethod
    def _parse_temperature(value: Optional[str]) -> float:
        if not value:
            return DEFAULT_TEMPERATURE
        try:
            temperature = float(value)
        except (TypeError, ValueError):
            return DEFAULT_TEMPERATURE
        if temperature < 0 or temperature > 2:
            return DEFAULT_TEMPERATURE
        return temperature

    @staticmethod
    def _parse_max_tokens(value: Optional[str]) -> Optional[int]:
        return LLMHandler._parse_positive_int(value)

    @staticmethod
    def _parse_positive_int(value: Optional[str]) -> Optional[int]:
        if not value:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """Send a text completion request to the configured LLM.

        Args:
            system_prompt: System-level instructions.
            user_prompt: User prompt content.
            json_mode: If True, request JSON-formatted response.
            temperature: Sampling temperature (lower = more deterministic).
            max_tokens: Optional output token limit.

        Returns:
            A dict with "text"/"raw" keys on success.
        """
        system_prompt = sanitize_prompt_text(system_prompt)
        user_prompt = sanitize_prompt_text(user_prompt)
        effective_temperature = (
            self.temperature if temperature is None else temperature
        )
        effective_max_tokens = self.max_tokens if max_tokens is None else max_tokens

        if self.provider == "ollama":
            request = self._ollama_complete(
                system_prompt,
                user_prompt,
                json_mode,
                effective_temperature,
                effective_max_tokens,
                self.num_ctx,
            )
        elif self.provider in OPENAI_COMPATIBLE_PROVIDERS:
            request = self._openai_complete(
                system_prompt,
                user_prompt,
                json_mode,
                effective_temperature,
                effective_max_tokens,
            )
        else:
            raise Exception(
                f"Provider {self.provider} not supported in direct mode. Use litellm."
            )
        self._in_flight += 1
        try:
            return await request
        finally:
            await self._after_request()

    async def _ollama_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
        max_tokens: Optional[int],
        num_ctx: Optional[int],
    ) -> dict[str, Any]:
        """Internal Ollama /api/chat implementation."""
        client = self.client
        url = "/api/chat"
        logger.info(f"Ollama calling: {url}, model: {self.model}")
        logger.debug(
            f"Ollama system[:200]={system_prompt[:200]!r} user[:200]={user_prompt[:200]!r}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens
        if num_ctx is not None:
            payload["options"]["num_ctx"] = num_ctx

        if json_mode:
            payload["format"] = "json"

        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            content = data.get("message", {}).get("content", "").strip()
            usage = data.get("prompt_eval_count"), data.get("eval_count")
            logger.debug(
                f"Ollama response[:300]={content[:300]!r} tokens(prompt,gen)={usage}"
            )
            await self._note_if_cut(
                system_prompt, user_prompt, data.get("prompt_eval_count"), num_ctx
            )

            if json_mode:
                return _loads_llm_json(content, f"{system_prompt}\n{user_prompt}")

            return {"text": content}
        except httpx.HTTPError as e:
            detail = _http_error_detail(e)
            logger.error(f"Ollama error connecting to {url}: {detail}")
            raise _llm_error_for(e, f"Ollama request failed: {detail}")

    async def _note_if_cut(
        self,
        system_prompt: str,
        user_prompt: str,
        evaluated: Optional[int],
        num_ctx: Optional[int],
    ) -> None:
        """Warn when Ollama dropped part of the prompt, and tell the running step."""
        if not evaluated:
            return
        window = num_ctx
        if window is None and evaluated >= _MIN_CUT_TOKENS:
            window = await self._ollama_window()
        prompt_chars = _prompt_chars(system_prompt, user_prompt)
        if not _prompt_was_cut(prompt_chars, evaluated, window):
            return
        logger.warning(
            "Ollama cut the prompt for %s to %s tokens%s: the instructions and "
            "option lists at its start were dropped. Raise the context window "
            "in the settings.",
            self.model,
            evaluated,
            f" of a {window}-token window" if window else "",
        )
        cuts = PROMPT_CUTS.get()
        if cuts is not None:
            cuts.append({"evaluated": evaluated, "window": window})

    async def _ollama_window(self) -> Optional[int]:
        """The context window Ollama loaded this model with, from /api/ps."""
        now = time.monotonic()
        if self._server_window_read_at is not None:
            wait = (
                _WINDOW_RECHECK_SECONDS
                if self._server_window
                else _WINDOW_RETRY_SECONDS
            )
            if now - self._server_window_read_at < wait:
                return self._server_window
        self._server_window_read_at = now
        window = None
        try:
            response = await self.client.get(
                "/api/ps", timeout=_WINDOW_LOOKUP_TIMEOUT
            )
            response.raise_for_status()
            wanted = {self.model, f"{self.model}:latest"}
            for loaded in response.json().get("models", []):
                if loaded.get("name") in wanted or loaded.get("model") in wanted:
                    window = int(loaded.get("context_length") or 0) or None
                    break
        except Exception as e:
            logger.debug("Could not read Ollama's context window: %s", e)
        self._server_window = window
        return window

    async def _openai_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
        max_tokens: Optional[int],
    ) -> dict[str, Any]:
        """Internal OpenAI-compatible /chat/completions implementation."""
        client = self.client
        url = "/chat/completions"
        logger.info(f"OpenAI calling: {url}, model: {self.model}")
        logger.debug(
            f"OpenAI system[:200]={system_prompt[:200]!r} user[:200]={user_prompt[:200]!r}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        # No response_format: LM Studio rejects json_object outright, and OpenAI
        # rejects it whenever the word "json" is missing from the prompt, which
        # users are free to edit away. The reply is parsed leniently instead.

        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            logger.debug(f"OpenAI response[:300]={content[:300]!r} tokens={usage}")

            if json_mode:
                return _loads_llm_json(content, f"{system_prompt}\n{user_prompt}")

            return {"text": content}
        except httpx.HTTPError as e:
            detail = _http_error_detail(e)
            logger.error(f"OpenAI error connecting to {url}: {detail}")
            raise _llm_error_for(e, f"OpenAI request failed: {detail}")

    async def vision_complete(
        self,
        system_prompt: str,
        user_prompt: str = "",
        images: Optional[list[bytes]] = None,
        pdf_bytes: Optional[bytes] = None,
        json_mode: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_page: Optional[Callable[[int, int], None]] = None,
    ) -> dict[str, Any]:
        """Send a vision/multimodal completion request.

        Args:
            system_prompt: System instructions.
            user_prompt: Optional text prompt.
            images: JPEG image bytes (Ollama provider).
            pdf_bytes: Raw PDF bytes (OpenAI provider, sent natively).
            json_mode: If True, request JSON-formatted response.
            temperature: Sampling temperature.
            max_tokens: Optional output token limit.

        Returns:
            A dict with extracted "text" or "raw".
        """
        system_prompt = sanitize_prompt_text(system_prompt)
        user_prompt = sanitize_prompt_text(user_prompt)
        if images is None:
            images = []
        effective_temperature = (
            self.temperature if temperature is None else temperature
        )
        effective_max_tokens = self.max_tokens if max_tokens is None else max_tokens

        if self.provider == "ollama":
            request = self._ollama_vision_complete(
                system_prompt,
                user_prompt,
                images,
                json_mode,
                effective_temperature,
                effective_max_tokens,
                self.num_ctx,
                on_page=on_page,
            )
        elif self.provider in OPENAI_COMPATIBLE_PROVIDERS:
            request = self._openai_vision_complete(
                system_prompt,
                user_prompt,
                images,
                json_mode,
                effective_temperature,
                effective_max_tokens,
                pdf_bytes=pdf_bytes if self.provider == "openai" else None,
                on_page=on_page,
            )
        else:
            raise Exception(f"Provider {self.provider} not supported for vision")
        self._in_flight += 1
        try:
            return await request
        finally:
            await self._after_request()

    async def _ollama_vision_complete(
        self,
        system_prompt: str,
        user_prompt: str = "",
        images: Optional[list[bytes]] = None,
        json_mode: bool = True,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        num_ctx: Optional[int] = None,
        on_page: Optional[Callable[[int, int], None]] = None,
    ) -> dict[str, Any]:
        """Ollama vision implementation — processes images page-by-page."""
        if images is None:
            images = []
        import base64

        client = self.client
        url = "/api/chat"
        combined_text = []

        for i, img in enumerate(images):
            _report_page(on_page, i + 1, len(images))
            img_b64 = base64.b64encode(img).decode("utf-8")
            logger.info(
                f"Ollama Vision page {i + 1}/{len(images)}: {url}, model: {self.model}"
            )

            messages = [
                {
                    "role": "user",
                    "content": system_prompt
                    if not user_prompt
                    else f"{system_prompt}\n\n{user_prompt}",
                    "images": [img_b64],
                },
            ]
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            }
            if max_tokens is not None:
                payload["options"]["num_predict"] = max_tokens
            if num_ctx is not None:
                payload["options"]["num_ctx"] = num_ctx
            if json_mode:
                payload["format"] = "json"

            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                cut_short = _incomplete_reason(data)
                if cut_short:
                    raise LLMError(
                        f"Ollama vision reply for page {i + 1} was cut short "
                        f"({cut_short}); the page was not fully read"
                    )
                content = data.get("message", {}).get("content", "").strip()
                combined_text.append(_drop_no_text_marker(content))
            except LLMError:
                raise
            except Exception as e:
                logger.error(
                    f"Ollama Vision error on page {i + 1}: {type(e).__name__}, {repr(e)}"
                )
                message = f"Ollama vision request failed on page {i + 1}: {repr(e)}"
                # Same shape as the text paths, so a run can tell a dead vision
                # endpoint from a document it simply could not read.
                if isinstance(e, httpx.HTTPError):
                    raise _llm_error_for(e, message)
                raise LLMError(message)

        full_text = "\n\n".join(combined_text)

        if json_mode:
            try:
                return json.loads(full_text)
            except json.JSONDecodeError:
                return {"raw": full_text}

        return {"text": full_text}

    async def _openai_vision_complete(
        self,
        system_prompt: str,
        user_prompt: str = "",
        images: Optional[list[bytes]] = None,
        json_mode: bool = True,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        pdf_bytes: Optional[bytes] = None,
        on_page: Optional[Callable[[int, int], None]] = None,
    ) -> dict[str, Any]:
        """OpenAI-compatible vision implementation — handles PDF and image inputs."""
        if images is None:
            images = []
        import base64

        client = self.client
        url = "/chat/completions"
        logger.info(f"OpenAI Vision calling: {url}, model: {self.model}")

        try:
            if not pdf_bytes:
                logger.info(
                    f"OpenAI Vision: sending JPEG images page-by-page ({len(images)} page(s))"
                )
                combined_text = []
                for page_no, img in enumerate(images, start=1):
                    _report_page(on_page, page_no, len(images))
                    img_b64 = base64.b64encode(img).decode("utf-8")
                    content = []
                    if user_prompt:
                        content.append({"type": "text", "text": user_prompt})
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                        }
                    )
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content},
                    ]
                    payload: dict[str, Any] = {
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    if max_tokens is not None:
                        payload["max_tokens"] = max_tokens

                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    cut_short = _incomplete_reason(data)
                    if cut_short:
                        raise LLMError(
                            f"OpenAI vision reply for page {page_no} was cut short "
                            f"({cut_short}); the page was not fully read"
                        )
                    content_text = data["choices"][0]["message"]["content"].strip()
                    combined_text.append(_drop_no_text_marker(content_text))

                full_text = "\n\n".join(combined_text)
                if json_mode:
                    try:
                        return json.loads(full_text)
                    except json.JSONDecodeError:
                        return {"raw": full_text}
                return {"text": full_text}

            logger.info("OpenAI Vision: sending PDF natively (all pages)")
            pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
            content: list[dict] = [
                {
                    "type": "file",
                    "file": {
                        "filename": "document.pdf",
                        "file_data": f"data:application/pdf;base64,{pdf_b64}",
                    },
                },
            ]
            if user_prompt:
                content.append({"type": "text", "text": user_prompt})

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ]

            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens

            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            cut_short = _incomplete_reason(data)
            if cut_short:
                raise LLMError(
                    f"OpenAI vision reply was cut short ({cut_short}); "
                    "the document was not fully read"
                )
            text_content = _drop_no_text_marker(
                data["choices"][0]["message"]["content"].strip()
            )

            if json_mode:
                try:
                    return json.loads(text_content)
                except json.JSONDecodeError:
                    return {"raw": text_content}

            return {"text": text_content}
        except httpx.HTTPError as e:
            detail = _http_error_detail(e)
            logger.error(f"OpenAI Vision error: {detail}")
            raise _llm_error_for(e, f"OpenAI vision request failed: {detail}")


class LLMHandlerManager:
    """Singleton manager for text and vision LLMHandler instances."""

    _text_handler: Optional["LLMHandler"] = None
    _vision_handler: Optional["LLMHandler"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def get_handler(cls, for_vision: bool = False) -> "LLMHandler":
        """Return the cached LLMHandler, creating one from config if needed."""
        attr = "_vision_handler" if for_vision else "_text_handler"
        handler = getattr(cls, attr)
        if handler is not None and not handler.is_closed:
            return handler
        async with cls._lock:
            handler = getattr(cls, attr)
            if handler is not None and not handler.is_closed:
                return handler
            handler = await LLMHandler.from_config(for_vision=for_vision)
            old = getattr(cls, attr)
            setattr(cls, attr, handler)
            if old is not None:
                try:
                    await old.close()
                except Exception:
                    pass
            return handler

    @classmethod
    async def close(cls):
        """Close both cached handlers and clear them."""
        async with cls._lock:
            for attr in ("_text_handler", "_vision_handler"):
                handler = getattr(cls, attr)
                if handler is not None:
                    try:
                        await handler.close()
                    except Exception:
                        pass
                    setattr(cls, attr, None)

    @classmethod
    async def reset(cls):
        """Drop both handlers so the next caller builds them from the settings.

        A document already running finishes on the old handler, which closes
        once its last request is done.
        """
        async with cls._lock:
            for attr in ("_text_handler", "_vision_handler"):
                handler = getattr(cls, attr)
                if handler is not None:
                    setattr(cls, attr, None)
                    try:
                        await handler.retire()
                    except Exception:
                        pass
