import os
import json
import httpx
from typing import Optional, Any
from ..models import Config
from ..database import get_session
from sqlmodel import select


class LLMHandler:
    def __init__(
        self,
        provider: str = "ollama",
        model: str = "llama3",
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.provider = provider
        self.model = model
        self.api_base = api_base or ""
        self.api_key = api_key

    @classmethod
    async def from_config(cls, for_vision: bool = False) -> "LLMHandler":
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

        print(f"[LLM Handler] Provider: {provider}, Model: {model}, API Base: {api_base}")

        return cls(provider=provider, model=model, api_base=api_base, api_key=api_key)

    @staticmethod
    async def _get_config(key: str) -> Optional[str]:
        # First try to get from database
        with get_session() as session:
            stmt = select(Config).where(Config.key == key)
            config = session.exec(stmt).first()
            if config and config.value:
                return config.value

        # Fallback to environment variable
        env_key = key.upper().replace("-", "_")
        return os.environ.get(env_key)

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = True,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        if self.provider == "ollama":
            return await self._ollama_complete(system_prompt, user_prompt, json_mode, temperature)
        elif self.provider in ("openai", "grok"):
            return await self._openai_complete(system_prompt, user_prompt, json_mode, temperature)
        else:
            raise Exception(f"Provider {self.provider} not supported in direct mode. Use litellm.")

    async def _ollama_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            url = f"{self.api_base}/api/chat"
            print(f"[Ollama] Calling: {url}")
            print(f"[Ollama] Model: {self.model}")

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                }
            }

            if json_mode:
                payload["format"] = "json"

            try:
                response = await client.post(url, json=payload, headers=self._build_headers())
                response.raise_for_status()
                data = response.json()

                content = data.get("message", {}).get("content", "").strip()

                if json_mode:
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {"raw": content}

                return {"text": content}
            except httpx.HTTPError as e:
                print(f"[Ollama] Error connecting to {url}: {str(e)}")
                raise Exception(f"Ollama request failed: {str(e)}")

    async def _openai_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            url = f"{self.api_base}/chat/completions"
            print(f"[OpenAI] Calling: {url}")
            print(f"[OpenAI] Model: {self.model}")

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }

            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            try:
                response = await client.post(url, json=payload, headers=self._build_headers())
                response.raise_for_status()
                data = response.json()

                content = data["choices"][0]["message"]["content"].strip()

                if json_mode:
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {"raw": content}

                return {"text": content}
            except httpx.HTTPError as e:
                print(f"[OpenAI] Error connecting to {url}: {str(e)}")
                raise Exception(f"OpenAI request failed: {str(e)}")

    async def vision_complete(
        self,
        system_prompt: str,
        user_prompt: str = "",
        images: list[bytes] = [],
        pdf_bytes: Optional[bytes] = None,
        json_mode: bool = True,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        if self.provider == "ollama":
            return await self._ollama_vision_complete(system_prompt, user_prompt, images, json_mode, temperature)
        elif self.provider in ("openai", "grok"):
            return await self._openai_vision_complete(system_prompt, user_prompt, images, json_mode, temperature, pdf_bytes=pdf_bytes if self.provider == "openai" else None)
        else:
            raise Exception(f"Provider {self.provider} not supported for vision")

    async def _ollama_vision_complete(
        self,
        system_prompt: str,
        user_prompt: str = "",
        images: list[bytes] = [],
        json_mode: bool = True,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        import base64

        url = f"{self.api_base}/api/chat"
        combined_text = []

        async with httpx.AsyncClient(timeout=120.0) as client:
            for i, img in enumerate(images):
                img_b64 = base64.b64encode(img).decode("utf-8")
                print(f"[Ollama Vision] Page {i+1}/{len(images)}: {url}, Model: {self.model}")

                messages = [
                    {"role": "user", "content": system_prompt if not user_prompt else f"{system_prompt}\n\n{user_prompt}", "images": [img_b64]},
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
                    response = await client.post(url, json=payload, headers=self._build_headers())
                    response.raise_for_status()
                    data = response.json()
                    content = data.get("message", {}).get("content", "").strip()
                    combined_text.append(content)
                except Exception as e:
                    print(f"[Ollama Vision] Error on page {i+1}: {type(e).__name__}, {repr(e)}")
                    raise Exception(f"Ollama vision request failed on page {i+1}: {repr(e)}")

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
        images: list[bytes] = [],
        json_mode: bool = True,
        temperature: float = 0.3,
        pdf_bytes: Optional[bytes] = None,
    ) -> dict[str, Any]:
        import base64

        async with httpx.AsyncClient(timeout=120.0) as client:
            url = f"{self.api_base}/chat/completions"
            print(f"[OpenAI Vision] Calling: {url}")
            print(f"[OpenAI Vision] Model: {self.model}")

            if pdf_bytes:
                print("[OpenAI Vision] Sending PDF natively (all pages)")
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
                print(f"[OpenAI Vision] Sending JPEG images (all {len(images)} page(s))")
                content = []
                if user_prompt:
                    content.append({"type": "text", "text": user_prompt})
                for img in images:
                    img_b64 = base64.b64encode(img).decode("utf-8")
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    })

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
                response = await client.post(url, json=payload, headers=self._build_headers())
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
                print(f"[OpenAI Vision] Error: {str(e)}")
                raise Exception(f"OpenAI vision request failed: {str(e)}")
