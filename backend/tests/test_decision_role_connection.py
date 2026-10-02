"""The decision model inherits the main connection as a group.

Empty provider: Ollama with the main URL and key, only the model may differ, so
Nimble on the same Ollama needs one field. Own provider: nothing of the main
connection travels with it, so a cloud key is never sent to another host.
"""

import pytest

from app.services.llm_handler import OPENROUTER_API_BASE, LLMHandler


@pytest.fixture
def rows(client):
    keys = [
        "llm_provider", "llm_model", "llm_api_base", "llm_api_key", "llm_timeout", "llm_num_ctx",
        "llm_provider_decision", "llm_model_decision", "llm_api_base_decision",
        "llm_api_key_decision", "llm_timeout_decision", "llm_num_ctx_decision", "llm_model_vision",
    ]

    def put(**values):
        for key in keys:
            client.delete(f"/api/config/{key}")
        for key, value in values.items():
            client.post("/api/config", json={"key": key, "value": value})

    yield put
    for key in keys:
        client.delete(f"/api/config/{key}")


def _build(client):
    return client.portal.call(LLMHandler.from_config, False, "decision")


def test_an_empty_provider_inherits_the_connection(client, rows):
    rows(llm_provider="ollama", llm_model="qwen2.5:7b", llm_api_base="http://main:11434",
         llm_api_key="main-key", llm_api_base_decision="http://ignored:1", llm_api_key_decision="ignored")
    h = _build(client)
    assert (h.provider, h.model, h.api_base, h.api_key) == ("ollama", "qwen2.5:7b", "http://main:11434", "main-key")


def test_only_the_model_may_differ_while_inherited(client, rows):
    rows(llm_provider="ollama", llm_model="qwen2.5:7b", llm_api_base="http://main:11434", llm_model_decision="nimble")
    h = _build(client)
    assert (h.model, h.api_base) == ("nimble", "http://main:11434")


def test_an_own_provider_inherits_nothing(client, rows):
    rows(llm_provider="ollama", llm_api_base="http://main:11434", llm_api_key="main-key",
         llm_provider_decision="openai", llm_model_decision="gpt-4o-mini")
    h = _build(client)
    assert (h.provider, h.model, h.api_base, h.api_key) == ("openai", "gpt-4o-mini", "", None)


def test_openrouter_gets_its_public_url(client, rows):
    rows(llm_provider_decision="openrouter", llm_model_decision="openai/gpt-4o-mini")
    assert _build(client).api_base == OPENROUTER_API_BASE


def test_an_inherited_openrouter_gets_its_public_url(client, rows):
    rows(llm_provider="openrouter", llm_api_key="main-key")
    h = _build(client)
    assert (h.provider, h.api_base, h.api_key, h.model) == ("openrouter", OPENROUTER_API_BASE, "main-key", "openai/gpt-4o-mini")


def test_an_own_provider_without_model_stays_empty(client, rows):
    rows(llm_provider_decision="openai", llm_api_base_decision="http://lmstudio:1234/v1")
    assert _build(client).model == ""


def test_timeout_and_window_fall_back_to_main(client, rows):
    rows(llm_provider="ollama", llm_timeout="120", llm_num_ctx="16384")
    h = _build(client)
    assert (h.timeout, h.num_ctx) == (120.0, 16384)
    rows(llm_provider="ollama", llm_timeout="120", llm_timeout_decision="30", llm_num_ctx_decision="8192")
    h = _build(client)
    assert (h.timeout, h.num_ctx) == (30.0, 8192)


def test_the_vision_role_is_unchanged(client, rows):
    rows(llm_provider="ollama", llm_api_base="http://main:11434", llm_model_vision="llava")
    h = client.portal.call(LLMHandler.from_config, True)
    assert (h.provider, h.api_base, h.model) == ("ollama", "http://main:11434", "llava")
