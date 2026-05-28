"""Tests for OpenRouter provider support in LLMHandler.

Covers:
- HTTP-Referer / X-Title attribution headers on the httpx client
- Dispatch through the OpenAI-compatible code path (text + vision)
- Sensible defaults from from_config when only the provider is set
- Non-openrouter providers do NOT get the OpenRouter headers
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.llm_handler import (
    OPENAI_COMPATIBLE_PROVIDERS,
    OPENROUTER_REFERER,
    OPENROUTER_TITLE,
    LLMHandler,
)


def test_openrouter_is_openai_compatible():
    """The shared provider set must include openrouter so test endpoints route correctly."""
    assert "openrouter" in OPENAI_COMPATIBLE_PROVIDERS
    assert "openai" in OPENAI_COMPATIBLE_PROVIDERS
    assert "grok" in OPENAI_COMPATIBLE_PROVIDERS


def test_openrouter_client_has_attribution_headers():
    """OpenRouter requests carry HTTP-Referer and X-Title for app attribution."""
    handler = LLMHandler(
        provider="openrouter",
        model="anthropic/claude-sonnet-4-6",
        api_base="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
    )
    headers = handler.client.headers
    assert headers["HTTP-Referer"] == OPENROUTER_REFERER
    assert headers["X-Title"] == OPENROUTER_TITLE
    assert headers["Authorization"] == "Bearer sk-or-test"


def test_openai_provider_does_not_get_openrouter_headers():
    """Plain OpenAI must not leak OpenRouter-specific headers."""
    handler = LLMHandler(
        provider="openai",
        model="gpt-4o-mini",
        api_base="https://api.openai.com/v1",
        api_key="sk-test",
    )
    headers = handler.client.headers
    assert "HTTP-Referer" not in headers
    assert "X-Title" not in headers


def test_grok_provider_does_not_get_openrouter_headers():
    """Grok must not leak OpenRouter-specific headers either."""
    handler = LLMHandler(
        provider="grok",
        model="grok-3-mini",
        api_base="https://api.x.ai/v1",
        api_key="xai-test",
    )
    headers = handler.client.headers
    assert "HTTP-Referer" not in headers
    assert "X-Title" not in headers


@pytest.mark.asyncio
async def test_openrouter_complete_routes_through_openai_path():
    """Text completion for openrouter must hit _openai_complete, not _ollama_complete."""
    handler = LLMHandler(provider="openrouter", model="openai/gpt-4o-mini")
    with (
        patch.object(
            handler, "_openai_complete", AsyncMock(return_value={"text": "ok"})
        ) as openai_mock,
        patch.object(
            handler, "_ollama_complete", AsyncMock(return_value={"text": "wrong"})
        ) as ollama_mock,
    ):
        result = await handler.complete("sys", "user")

    assert result == {"text": "ok"}
    openai_mock.assert_awaited_once()
    ollama_mock.assert_not_called()


@pytest.mark.asyncio
async def test_openrouter_vision_routes_through_openai_vision_path():
    """Vision completion for openrouter must hit _openai_vision_complete with no pdf_bytes."""
    handler = LLMHandler(provider="openrouter", model="openai/gpt-4o")
    with patch.object(
        handler,
        "_openai_vision_complete",
        AsyncMock(return_value={"text": "ok"}),
    ) as vision_mock:
        await handler.vision_complete(
            "sys",
            user_prompt="user",
            images=[b"jpg-bytes"],
            pdf_bytes=b"pdf-bytes",
        )

    vision_mock.assert_awaited_once()
    # pdf_bytes must be stripped for non-openai providers — OpenRouter proxies many
    # backends and PDF-native upload is OpenAI-direct only.
    _, kwargs = vision_mock.call_args
    assert kwargs["pdf_bytes"] is None


@pytest.mark.asyncio
async def test_openai_vision_keeps_pdf_bytes():
    """Sanity check: openai provider still receives pdf_bytes natively."""
    handler = LLMHandler(provider="openai", model="gpt-4o")
    with patch.object(
        handler,
        "_openai_vision_complete",
        AsyncMock(return_value={"text": "ok"}),
    ) as vision_mock:
        await handler.vision_complete(
            "sys",
            images=[b"jpg-bytes"],
            pdf_bytes=b"pdf-bytes",
        )

    _, kwargs = vision_mock.call_args
    assert kwargs["pdf_bytes"] == b"pdf-bytes"


@pytest.mark.asyncio
async def test_openrouter_from_config_uses_namespaced_default_model():
    """When only provider=openrouter is configured, default model uses vendor/model namespace."""
    configs = {
        "llm_provider": "openrouter",
        "llm_model": None,
        "llm_api_base": "https://openrouter.ai/api/v1",
        "llm_api_key": "sk-or-test",
    }

    async def fake_get_config(key: str):
        return configs.get(key)

    with patch.object(LLMHandler, "_get_config", side_effect=fake_get_config):
        handler = await LLMHandler.from_config(for_vision=False)

    assert handler.provider == "openrouter"
    assert handler.model == "openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_openrouter_from_config_vision_default_model():
    """Vision default for openrouter also uses vendor/model namespace."""
    configs = {
        "llm_provider_vision": "openrouter",
        "llm_model_vision": None,
        "llm_api_base_vision": "https://openrouter.ai/api/v1",
        "llm_api_key_vision": "sk-or-test",
    }

    async def fake_get_config(key: str):
        return configs.get(key)

    with patch.object(LLMHandler, "_get_config", side_effect=fake_get_config):
        handler = await LLMHandler.from_config(for_vision=True)

    assert handler.provider == "openrouter"
    assert handler.model == "openai/gpt-4o"
