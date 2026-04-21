"""LLM client supporting Ollama and OpenAI-compatible APIs (including Grok).

Provides text completion (with optional JSON mode) and vision multimodal
completion. LLMHandler instances are managed by the singleton LLMHandlerManager.
"""

import asyncio
import logging
import json
import httpx
from typing import Optional, Any
from ..exceptions import LLMUnavailableError

logger = logging.getLogger(__name__)


class LLMHandler:
    """HTTP client for LLM inference via Ollama or OpenAI-compatible APIs.

    Attributes:
        provider: "ollama", "openai", or "grok".
        model: Model name passed to the API.
        api_base: Base URL for the API endpoint.
        api_key: Optional API key for authenticated endpoints.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "llama3",
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 600.0,
    ):
        self.provider = provider
        self.model = model
        self.api_base = api_base or ""
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._closed = False

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
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

    @classmethod
    async def from_config(cls, for_vision: bool = False) -> "LLMHandler":
        """Construct a LLMHandler from the application config.

        Args:
            for_vision: If True, use the vision-specific config keys (_vision suffix).

        Returns:
            A configured LLMHandler instance.
        """
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
            model = "llama3" if not for_vision else "llava"

        timeout_str = await cls._get_config(f"llm_timeout{suffix}")
        if for_vision and not timeout_str:
            timeout_str = await cls._get_config("llm_timeout")
        timeout = float(timeout_str) if timeout_str else 600.0

        logger.info(f"Provider: {provider}, Model: {model}, API Base: {api_base}")

        return cls(
            provider=provider,
            model=model,
            api_base=api_base,
            api_key=api_key,
            timeout=timeout,
        )

    @staticmethod
    async def _get_config(key: str) -> Optional[str]:
        from .config_cache import ConfigCache

        cache = await ConfigCache.get_instance()
        return await cache.get(key)

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = True,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Send a text completion request to the configured LLM.

        Args:
            system_prompt: System-level instructions.
            user_prompt: User prompt content.
            json_mode: If True, request JSON-formatted response.
            temperature: Sampling temperature (lower = more deterministic).

        Returns:
            A dict with "text"/"raw" keys on success.
        """
        if self.provider == "ollama":
            return await self._ollama_complete(
                system_prompt, user_prompt, json_mode, temperature
            )
        elif self.provider in ("openai", "grok"):
            return await self._openai_complete(
                system_prompt, user_prompt, json_mode, temperature
            )
        else:
            raise Exception(
                f"Provider {self.provider} not supported in direct mode. Use litellm."
            )

    async def _ollama_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
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

            if json_mode:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"raw": content}

            return {"text": content}
        except httpx.HTTPError as e:
            logger.error(f"Ollama error connecting to {url}: {str(e)}")
            raise LLMUnavailableError(f"Ollama request failed: {str(e)}")

    async def _openai_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
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

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            logger.debug(f"OpenAI response[:300]={content[:300]!r} tokens={usage}")

            if json_mode:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"raw": content}

            return {"text": content}
        except httpx.HTTPError as e:
            logger.error(f"OpenAI error connecting to {url}: {str(e)}")
            raise LLMUnavailableError(f"OpenAI request failed: {str(e)}")

    async def vision_complete(
        self,
        system_prompt: str,
        user_prompt: str = "",
        images: Optional[list[bytes]] = None,
        pdf_bytes: Optional[bytes] = None,
        json_mode: bool = True,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Send a vision/multimodal completion request.

        Args:
            system_prompt: System instructions.
            user_prompt: Optional text prompt.
            images: JPEG image bytes (Ollama provider).
            pdf_bytes: Raw PDF bytes (OpenAI provider, sent natively).
            json_mode: If True, request JSON-formatted response.
            temperature: Sampling temperature.

        Returns:
            A dict with extracted "text" or "raw".
        """
        if images is None:
            images = []
        if self.provider == "ollama":
            return await self._ollama_vision_complete(
                system_prompt, user_prompt, images, json_mode, temperature
            )
        elif self.provider in ("openai", "grok"):
            return await self._openai_vision_complete(
                system_prompt,
                user_prompt,
                images,
                json_mode,
                temperature,
                pdf_bytes=pdf_bytes if self.provider == "openai" else None,
            )
        else:
            raise Exception(f"Provider {self.provider} not supported for vision")

    async def _ollama_vision_complete(
        self,
        system_prompt: str,
        user_prompt: str = "",
        images: Optional[list[bytes]] = None,
        json_mode: bool = True,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Ollama vision implementation — processes images page-by-page."""
        if images is None:
            images = []
        import base64

        client = self.client
        url = "/api/chat"
        combined_text = []

        for i, img in enumerate(images):
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
            if json_mode:
                payload["format"] = "json"

            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                content = data.get("message", {}).get("content", "").strip()
                combined_text.append(content)
            except Exception as e:
                logger.error(
                    f"Ollama Vision error on page {i + 1}: {type(e).__name__}, {repr(e)}"
                )
                raise Exception(
                    f"Ollama vision request failed on page {i + 1}: {repr(e)}"
                )

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
        temperature: float = 0.3,
        pdf_bytes: Optional[bytes] = None,
    ) -> dict[str, Any]:
        """OpenAI-compatible vision implementation — handles PDF and image inputs."""
        if images is None:
            images = []
        import base64

        client = self.client
        url = "/chat/completions"
        logger.info(f"OpenAI Vision calling: {url}, model: {self.model}")

        if pdf_bytes:
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
        else:
            logger.info(
                f"OpenAI Vision: sending JPEG images (all {len(images)} page(s))"
            )
            content = []
            if user_prompt:
                content.append({"type": "text", "text": user_prompt})
            for img in images:
                img_b64 = base64.b64encode(img).decode("utf-8")
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

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            text_content = data["choices"][0]["message"]["content"].strip()

            if json_mode:
                try:
                    return json.loads(text_content)
                except json.JSONDecodeError:
                    return {"raw": text_content}

            return {"text": text_content}
        except httpx.HTTPError as e:
            logger.error(f"OpenAI Vision error: {str(e)}")
            raise Exception(f"OpenAI vision request failed: {str(e)}")


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
        """Close all handlers (alias for LLMHandlerManager.close)."""
        await cls.close()
