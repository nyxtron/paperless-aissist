"""A decision setting saved in the web UI reaches the next document.

The service is cached like the LLM handler, so every key it is built from has
to drop it, including the main LLM keys it falls back to. A spy on the config
cache proves nothing the service reads is missing from that set.
"""

import asyncio
from unittest.mock import patch

import httpx
import pytest

from app.routers.config import DECISION_SERVICE_KEYS, LLM_HANDLER_KEYS
from app.services.config_cache import ConfigCache
from app.services.decision import DecisionService, DecisionServiceManager
from app.services.decision.adapters import OllamaLettersAdapter, OllamaNimbleAdapter
from app.services.llm_handler import LLMHandler


@pytest.fixture
def cached_service():
    handler = LLMHandler(provider="ollama", model="m", api_base="http://x")
    service = DecisionService(handler, OllamaLettersAdapter, None, None)
    DecisionServiceManager._service = service
    yield service
    DecisionServiceManager._service = None


@pytest.fixture
def clean(client):
    keys = ["llm_provider_decision", "llm_model_decision", "llm_api_base_decision", "llm_api_key_decision",
            "llm_timeout_decision", "llm_num_ctx_decision", "decision_format", "decision_threshold_correspondent",
            "llm_provider", "llm_model", "llm_api_base", "tag_blacklist"]
    yield
    for key in keys:
        client.delete(f"/api/config/{key}")


@pytest.mark.parametrize("key,value", [
    ("llm_model_decision", "nimble"), ("llm_provider_decision", "openai"), ("llm_api_base_decision", "http://a"),
    ("llm_api_key_decision", "k"), ("llm_timeout_decision", "30"), ("llm_num_ctx_decision", "8192"),
    ("decision_format", "nimble"), ("llm_model", "qwen3:8b"), ("llm_api_base", "http://b"), ("llm_provider", "ollama"),
])
def test_saving_a_setting_drops_the_service(client, cached_service, clean, key, value):
    assert client.post("/api/config", json={"key": key, "value": value}).status_code == 200
    assert DecisionServiceManager._service is None
    assert cached_service.is_closed


def test_clearing_a_setting_drops_the_service(client, cached_service, clean):
    client.post("/api/config", json={"key": "llm_model_decision", "value": "nimble"})
    DecisionServiceManager._service = cached_service
    client.delete("/api/config/llm_model_decision")
    assert DecisionServiceManager._service is None


def test_other_settings_leave_it_alone(client, cached_service, clean):
    client.post("/api/config", json={"key": "decision_threshold_correspondent", "value": "0.8"})
    client.post("/api/config", json={"key": "tag_blacklist", "value": "x"})
    assert DecisionServiceManager._service is cached_service


def test_every_key_the_service_reads_is_in_the_reset_set(client, clean):
    client.post("/api/config", json={"key": "llm_provider_decision", "value": "ollama"})
    client.post("/api/config", json={"key": "llm_model_decision", "value": "nimble"})
    seen = []
    real_get = ConfigCache.get

    async def spy(self, key, default=""):
        seen.append(key)
        return await real_get(self, key, default)

    with patch.object(ConfigCache, "get", spy):
        client.portal.call(DecisionService.from_config)
    assert seen and set(seen) <= (LLM_HANDLER_KEYS | DECISION_SERVICE_KEYS), set(seen) - (LLM_HANDLER_KEYS | DECISION_SERVICE_KEYS)


def test_the_main_connection_with_a_nimble_model(client, clean):
    client.post("/api/config", json={"key": "llm_provider", "value": "ollama"})
    client.post("/api/config", json={"key": "llm_api_base", "value": "http://main:11434"})
    client.post("/api/config", json={"key": "llm_model_decision", "value": "nimble"})
    s = client.portal.call(DecisionService.from_config)
    assert (s.provider, s.model, s.method, s._fallback_reason) == ("ollama", "nimble", "ollama_nimble", None)


def test_an_own_provider_without_url_falls_back(client, clean):
    client.post("/api/config", json={"key": "llm_provider_decision", "value": "openai"})
    client.post("/api/config", json={"key": "llm_model_decision", "value": "gpt-4o-mini"})
    assert client.portal.call(DecisionService.from_config)._fallback_reason == "url_missing"


def test_an_own_openrouter_needs_no_url(client, clean):
    client.post("/api/config", json={"key": "llm_provider_decision", "value": "openrouter"})
    client.post("/api/config", json={"key": "llm_model_decision", "value": "openai/gpt-4o-mini"})
    s = client.portal.call(DecisionService.from_config)
    assert (s.method, s._fallback_reason) == ("openai_letters", None)


def test_an_own_provider_without_model_falls_back(client, clean):
    client.post("/api/config", json={"key": "llm_provider_decision", "value": "openai"})
    client.post("/api/config", json={"key": "llm_api_base_decision", "value": "http://lm:1234/v1"})
    assert client.portal.call(DecisionService.from_config)._fallback_reason == "model_missing"


@pytest.mark.asyncio
async def test_a_running_request_finishes_across_a_reset():
    started, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        started.set()
        await release.wait()
        return httpx.Response(200, json={"logprobs": [{"top_logprobs": [{"token": "A", "logprob": 0.0}]}]})

    handler = LLMHandler(provider="ollama", model="m", api_base="http://x")
    handler._client = httpx.AsyncClient(base_url="http://x", transport=httpx.MockTransport(respond))
    # Nimble needs no prompt row, so the service can run without a loader.
    service = DecisionService(handler, OllamaNimbleAdapter, None, None)
    DecisionServiceManager._service = service
    try:
        running = asyncio.create_task(service.decide("t", "correspondent", ["X"], question="Q?", threshold=0.9))
        await asyncio.wait_for(started.wait(), 5)
        await DecisionServiceManager.reset()
        assert DecisionServiceManager._service is None and not handler._client.is_closed
        release.set()
        d = await running
        assert d.index == 0 and handler._client.is_closed
    finally:
        DecisionServiceManager._service = None


def test_the_verdict_expires_and_the_probe_clears_it(cached_service):
    cached_service._unsupported = ("no_logprobs", None)
    cached_service._unsupported_until = 10.0
    with patch("app.services.decision.service.time.monotonic", lambda: 5.0):
        assert cached_service._remembered_unsupported() == ("no_logprobs", None)
    with patch("app.services.decision.service.time.monotonic", lambda: 11.0):
        assert cached_service._remembered_unsupported() is None
    cached_service._unsupported_until = 10.0
    cached_service.forget_unsupported()
    assert cached_service._unsupported_until is None


@pytest.mark.asyncio
async def test_the_probe_sends_even_when_unsupported_was_remembered():
    reply = {"logprobs": [{"top_logprobs": [{"token": "A", "logprob": 0.0}]}], "prompt_eval_count": 5}
    handler = LLMHandler(provider="ollama", model="nimble", api_base="http://x")
    calls = []

    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=reply)

    handler._client = httpx.AsyncClient(base_url="http://x", transport=httpx.MockTransport(respond))
    service = DecisionService(handler, OllamaNimbleAdapter, None, None)
    service._unsupported = ("no_logprobs", None)
    service._unsupported_until = float("inf")
    d = await service.probe()
    assert calls == ["/api/chat"] and d.index == 0 and service._unsupported_until is None


def test_threshold_saves_are_validated(client, clean):
    r = client.post("/api/config", json={"key": "decision_threshold_correspondent", "value": "abc"})
    assert r.status_code == 400 and "0.50" in r.json()["detail"]
    r = client.post("/api/config", json={"key": "decision_threshold_correspondent", "value": "1.5"})
    assert r.status_code == 200 and r.json()["value"] == "1.00"
    r = client.post("/api/config", json={"key": "decision_threshold_correspondent", "value": "0.3"})
    assert r.json()["value"] == "0.50"
    r = client.post("/api/config", json={"key": "decision_threshold_correspondent", "value": "0.85"})
    assert r.json()["value"] == "0.85"


def test_the_test_endpoint_reports_a_probe_and_the_review_tag(client, clean, monkeypatch):
    from app.routers import config as config_router
    from app.services.decision.service import Decision

    async def fake_probe(self):
        return Decision("ollama_letters", "ollama", "m", index=0, choice="Stadtwerke Saarbrücken",
                        probability=0.998, rendered="[user]\n...", requests=1)

    class FakePaperless:
        async def get_tags(self, force_refresh=False):
            return [{"id": 1, "name": "ai-review"}]

    async def fake_client():
        return FakePaperless()

    monkeypatch.setattr(DecisionService, "probe", fake_probe)
    monkeypatch.setattr(config_router.PaperlessClientManager, "get_client", fake_client)
    DecisionServiceManager._service = DecisionService(LLMHandler(provider="ollama", model="m", api_base="http://x"),
                                                      OllamaLettersAdapter, None, None)
    try:
        r = client.post("/api/config/test-decision")
    finally:
        DecisionServiceManager._service = None
    body = r.json()
    assert body["success"] is True and body["choice"] == "Stadtwerke Saarbrücken" and body["probability"] == 0.998
    assert body["review_tag"] == {"name": "ai-review", "exists": True}
