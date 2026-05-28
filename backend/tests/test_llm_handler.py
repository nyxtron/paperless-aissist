import pytest

from app.services.llm_handler import LLMHandler


class DummyResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class DummyClient:
    is_closed = False

    def __init__(self, response_data):
        self.response_data = response_data
        self.payloads = []

    async def post(self, url, json):
        self.payloads.append(json)
        return DummyResponse(self.response_data)


@pytest.mark.asyncio
async def test_ollama_max_tokens_uses_num_predict():
    client = DummyClient({"message": {"content": "ok"}})
    handler = LLMHandler(provider="ollama", model="test", max_tokens=4092)
    handler._client = client

    await handler.complete("system", "user", json_mode=False)

    assert client.payloads[0]["options"]["num_predict"] == 4092


@pytest.mark.asyncio
async def test_openai_max_tokens_uses_max_tokens():
    client = DummyClient({"choices": [{"message": {"content": "ok"}}]})
    handler = LLMHandler(provider="openai", model="test", max_tokens=4092)
    handler._client = client

    await handler.complete("system", "user", json_mode=False)

    assert client.payloads[0]["max_tokens"] == 4092


@pytest.mark.asyncio
async def test_ollama_vision_max_tokens_uses_num_predict():
    client = DummyClient({"message": {"content": "ok"}})
    handler = LLMHandler(provider="ollama", model="test", max_tokens=4092)
    handler._client = client

    await handler.vision_complete("system", images=[b"image"], json_mode=False)

    assert client.payloads[0]["options"]["num_predict"] == 4092


@pytest.mark.asyncio
async def test_ollama_temperature_can_be_zero():
    client = DummyClient({"message": {"content": "ok"}})
    handler = LLMHandler(provider="ollama", model="test", temperature=0.0)
    handler._client = client

    await handler.complete("system", "user", json_mode=False)

    assert client.payloads[0]["options"]["temperature"] == 0.0


@pytest.mark.asyncio
async def test_openai_temperature_uses_configured_value():
    client = DummyClient({"choices": [{"message": {"content": "ok"}}]})
    handler = LLMHandler(provider="openai", model="test", temperature=0.1)
    handler._client = client

    await handler.complete("system", "user", json_mode=False)

    assert client.payloads[0]["temperature"] == 0.1


@pytest.mark.asyncio
async def test_vision_max_tokens_can_use_env_alias(monkeypatch):
    async def fake_get_config(key):
        return "4092" if key == "vision_llm_max_tokens" else ""

    monkeypatch.setattr(LLMHandler, "_get_config", staticmethod(fake_get_config))

    handler = await LLMHandler.from_config(for_vision=True)

    assert handler.max_tokens == 4092


@pytest.mark.asyncio
async def test_vision_temperature_can_use_env_alias(monkeypatch):
    async def fake_get_config(key):
        return "0" if key == "vision_llm_temperature" else ""

    monkeypatch.setattr(LLMHandler, "_get_config", staticmethod(fake_get_config))

    handler = await LLMHandler.from_config(for_vision=True)

    assert handler.temperature == 0.0
