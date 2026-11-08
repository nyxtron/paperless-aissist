"""Format "Auto" with an Ollama decision model such as clef-flash.

Such a model refuses /api/chat, so Auto has to send it to /v1/systemone. What
the model can do comes from Ollama's /api/show, asked once when the first
document needs a decision. Until Ollama has answered, a refusal on /api/chat
falls back to the text prompt instead of failing the run.
"""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.decision import DecisionService
from app.services.decision.adapters import OllamaLettersAdapter
from app.services.llm_handler import LLMHandler

MODEL = "clef-flash:9b-q8_0"
SETTINGS = {"llm_provider": "ollama", "llm_api_base": "http://main:11434",
            "llm_model_decision": MODEL, "decision_format": "auto"}
REFUSAL = {"error": f'"{MODEL}" does not support chat'}
LETTER_B = {"logprobs": [{"top_logprobs": [{"token": "B", "logprob": 0.0}]}]}


@pytest.fixture
def clef_settings(client):
    for key, value in SETTINGS.items():
        client.post("/api/config", json={"key": key, "value": value})
    yield
    for key in SETTINGS:
        client.delete(f"/api/config/{key}")


@pytest.fixture
def clock(monkeypatch):
    # The service's clock only: patching time.monotonic itself would stop the
    # event loop's clock too, and a broken route would hang instead of fail.
    now = [1000.0]
    monkeypatch.setattr("app.services.decision.service.time", SimpleNamespace(monotonic=lambda: now[0]))
    return now


async def letter_prompt(field):
    return {"system_prompt": "", "user_template": "{content}\n{question}\n{options}"}


def systemone_answer(request):
    answers = {}
    for name, q in json.loads(request.content)["questions"].items():
        keys = list(q["criteria"])
        answers[name] = {"type": "choice", "choice": keys[1],
                         "probabilities": {k: (0.97 if k == keys[1] else 0.03 / (len(keys) - 1)) for k in keys}}
    return httpx.Response(200, json={"answers": answers, "usage": {"input_tokens": 40, "output_tokens": 0}})


class Ollama:
    """Answers like Ollama 0.35.1; /api/show replies in order, /api/chat as given."""

    def __init__(self, *show, chat=(400, REFUSAL), model=MODEL):
        self.show = list(show)
        self.chat = chat
        self.model = model
        self.calls = []
        self.chat_started = asyncio.Event()
        self.release_chat = None

    async def __call__(self, request):
        self.calls.append(request.url.path)
        if request.url.path == "/api/show":
            # Ollama only answers a POST that names the model.
            assert request.method == "POST" and json.loads(request.content) == {"model": self.model}
            status, body = self.show.pop(0)
            return httpx.Response(status, json=body)
        if request.url.path == "/v1/systemone":
            return systemone_answer(request)
        self.chat_started.set()
        if self.release_chat is not None:
            await self.release_chat.wait()
        return httpx.Response(self.chat[0], json=self.chat[1])


def _attach(service, ollama):
    service._handler._client = httpx.AsyncClient(base_url="http://main:11434", transport=httpx.MockTransport(ollama))
    return service


def _service(client, ollama):
    return _attach(client.portal.call(DecisionService.from_config), ollama)


def _direct(ollama, model=MODEL):
    """The service from_config builds under auto, without the settings round trip."""
    handler = LLMHandler(provider="ollama", model=model, api_base="http://main:11434")
    return _attach(DecisionService(handler, OllamaLettersAdapter, None, letter_prompt, ask_capabilities=True), ollama)


async def _ask(service):
    return await service.decide("Rechnung der Energis", "correspondent", ["Telekom", "Energis", "AOK"],
                                question="Who sent it?", threshold=0.9)


def _decide(client, service):
    return client.portal.call(_ask, service)


async def _overlap(service, ollama, clock):
    """A waits on /api/chat while B, a minute later, learns the route; then A's answer comes back."""
    ollama.release_chat = asyncio.Event()
    a = asyncio.create_task(_ask(service))
    try:
        await asyncio.wait_for(ollama.chat_started.wait(), 5)
        clock[0] += 61
        # Were B sent to /api/chat as well, it would wait for A's release.
        b = await asyncio.wait_for(_ask(service), 5)
    finally:
        ollama.release_chat.set()
    return await asyncio.wait_for(a, 5), b


def test_a_decision_model_is_asked_on_its_own_route(client, clef_settings):
    ollama = Ollama((200, {"capabilities": ["decision", "vision"]}))
    service = _service(client, ollama)
    d = _decide(client, service)
    assert ollama.calls == ["/api/show", "/v1/systemone"]
    assert (d.method, d.choice, d.fallback_reason) == ("ollama_systemone", "Energis", None)
    assert d.probability == pytest.approx(0.97)
    # Ollama is asked once; the next document goes straight to the route.
    _decide(client, service)
    assert ollama.calls == ["/api/show", "/v1/systemone", "/v1/systemone"]


def test_an_ordinary_model_keeps_the_letters_and_is_asked_once(client, clef_settings):
    client.post("/api/config", json={"key": "llm_model_decision", "value": "qwen2.5:7b"})
    ollama = Ollama((200, {"capabilities": ["completion", "tools"]}), chat=(200, LETTER_B), model="qwen2.5:7b")
    service = _service(client, ollama)
    service._prompt_loader = letter_prompt
    first, second = _decide(client, service), _decide(client, service)
    assert ollama.calls == ["/api/show", "/api/chat", "/api/chat"]
    assert (first.method, first.choice, second.choice) == ("ollama_letters", "Energis", "Energis")


def test_until_ollama_answers_a_refusal_falls_back_and_auto_tries_again(client, clef_settings, clock):
    ollama = Ollama((503, {"error": "busy"}), (200, {"capabilities": ["decision"]}))
    service = _service(client, ollama)
    first = _decide(client, service)
    assert ollama.calls == ["/api/show", "/api/chat"]
    assert (first.fallback_reason, first.choice) == ("format_unsupported", None)
    # Ollama is not asked again before a minute is up; the refusal stands meanwhile.
    clock[0] += 30
    assert _decide(client, service).fallback_reason == "format_unsupported"
    assert ollama.calls == ["/api/show", "/api/chat"]
    # Then knowing the route lifts the refusal.
    clock[0] += 31
    second = _decide(client, service)
    assert ollama.calls == ["/api/show", "/api/chat", "/api/show", "/v1/systemone"]
    assert (second.method, second.choice, second.fallback_reason) == ("ollama_systemone", "Energis", None)


def test_the_settings_test_asks_ollama_again_right_away(client, clef_settings, clock):
    ollama = Ollama((503, {"error": "busy"}), (200, {"capabilities": ["decision"]}))
    service = _service(client, ollama)
    _decide(client, service)
    d = client.portal.call(service.probe)
    assert ollama.calls == ["/api/show", "/api/chat", "/api/show", "/v1/systemone"]
    assert (d.method, d.fallback_reason) == ("ollama_systemone", None)


@pytest.mark.parametrize("fmt,route", [("systemone", "/v1/systemone"), ("letters", "/api/chat")])
def test_a_format_chosen_by_hand_is_not_second_guessed(client, clef_settings, fmt, route):
    client.post("/api/config", json={"key": "decision_format", "value": fmt})
    ollama = Ollama((200, {"capabilities": ["decision"]}))
    service = _service(client, ollama)
    service._prompt_loader = letter_prompt
    _decide(client, service)
    assert ollama.calls == [route]


@pytest.mark.asyncio
async def test_a_late_refusal_from_the_old_route_is_not_remembered(clock):
    # Document A went to letters while Ollama did not answer; B learns the route
    # a minute later, before A's refusal comes back.
    ollama = Ollama((503, {"error": "busy"}), (200, {"capabilities": ["decision"]}))
    service = _direct(ollama)
    a, b = await _overlap(service, ollama, clock)
    c = await asyncio.wait_for(_ask(service), 5)
    assert (a.method, a.fallback_reason) == ("ollama_letters", "format_unsupported")
    assert (b.method, b.choice) == ("ollama_systemone", "Energis")
    assert (c.method, c.choice, c.fallback_reason) == ("ollama_systemone", "Energis", None)


@pytest.mark.asyncio
async def test_a_decision_names_the_route_it_took(clock):
    # A copy of nimble under another name answers on both routes.
    ollama = Ollama((503, {"error": "busy"}), (200, {"capabilities": ["decision"]}), chat=(200, LETTER_B), model="decider")
    service = _direct(ollama, model="decider")
    a, b = await _overlap(service, ollama, clock)
    assert (a.method, a.choice) == ("ollama_letters", "Energis")
    assert b.method == "ollama_systemone"


@pytest.mark.asyncio
async def test_a_settings_save_does_not_cut_the_lookup_short():
    started, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        started.set()
        await release.wait()
        return httpx.Response(200, json={"capabilities": ["decision"]})

    handler = LLMHandler(provider="ollama", model=MODEL, api_base="http://main:11434")
    handler._client = httpx.AsyncClient(base_url="http://main:11434", transport=httpx.MockTransport(respond))
    lookup = asyncio.create_task(handler.ollama_capabilities())
    await asyncio.wait_for(started.wait(), 5)
    await handler.retire()
    assert not handler._client.is_closed
    release.set()
    assert await lookup == ["decision"]
    assert handler._client.is_closed
