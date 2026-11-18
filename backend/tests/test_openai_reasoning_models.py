"""OpenAI's gpt-5 and gpt-6 models take other parameters than the older ones.

They refuse max_tokens, and with reasoning on they spend a one-token answer on
thinking and return no token probabilities, so decision mode has a switch that
turns reasoning off. The first two refusals below are the ones reported in
issue #59; the others are worded after OpenAI's reference, they were not
captured from the API.
"""

import json

import httpx
import pytest

from app.exceptions import LLMHttpError
from app.services.decision import DecisionService, DecisionServiceManager
from app.services.decision.adapters import DecisionUnsupported, OpenAILettersAdapter
from app.services.decision.formats import NONE_DESCRIPTION, NONE_LABEL
from app.services.llm_handler import LLMHandler

OPENAI = "https://api.openai.com/v1"
PROMPT = {"system_prompt": "Answer with the letter.", "user_template": "Doc:\n{content}\n{question}\n{options}\nLetter only."}
ASK = [("c0", ["Amazon", "Telekom", NONE_LABEL])]
DESC = {NONE_LABEL: NONE_DESCRIPTION}

MAX_TOKENS_REFUSED = {"error": {
    "message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.",
    "type": "invalid_request_error", "param": "max_tokens", "code": "unsupported_parameter"}}
MODEL_RETIRED = {"error": {
    "message": "The model `gpt-4.1-nano` has been deprecated, learn more here: https://platform.openai.com/docs/deprecations",
    "type": "invalid_request_error", "param": None, "code": "model_not_found"}}
LOGPROBS_REFUSED = {"error": {
    "message": "'logprobs' is not supported with this model.",
    "type": "invalid_request_error", "param": "logprobs", "code": "unsupported_parameter"}}
REASONING_UNKNOWN = {"error": {
    "message": "Unrecognized request argument supplied: reasoning_effort",
    "type": "invalid_request_error", "param": None, "code": None}}
LETTER = {"choices": [{"finish_reason": "length", "message": {"content": "A"}, "logprobs": {"content": [
    {"token": "A", "logprob": -0.01, "top_logprobs": [{"token": "A", "logprob": -0.01}, {"token": "B", "logprob": -5.0}]}]}}],
    "usage": {"prompt_tokens": 60}}
TEXT = {"choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]}


class OpenAI:
    """Answers like api.openai.com does for the models named in the issue."""

    def __init__(self):
        self.bodies = []

    def __call__(self, request):
        body = json.loads(request.content)
        self.bodies.append(body)
        model = body["model"]
        if model == "gpt-4.1-nano":
            return httpx.Response(404, json=MODEL_RETIRED)
        if model.startswith("gpt-6"):
            if "max_tokens" in body:
                return httpx.Response(400, json=MAX_TOKENS_REFUSED)
            if body.get("logprobs") and body.get("reasoning_effort") != "none":
                return httpx.Response(400, json=LOGPROBS_REFUSED)
        elif "reasoning_effort" in body:
            return httpx.Response(400, json=REASONING_UNKNOWN)
        return httpx.Response(200, json=LETTER if body.get("logprobs") else TEXT)


def _handler(server, model="gpt-6-luna", api_base=OPENAI, **settings):
    handler = LLMHandler(provider="openai", model=model, api_base=api_base, **settings)
    handler._client = httpx.AsyncClient(base_url=api_base, transport=httpx.MockTransport(server))
    return handler


class TestTheOutputLimitName:
    @pytest.mark.asyncio
    async def test_a_text_request_to_openai_uses_the_new_name(self):
        server = OpenAI()
        assert await _handler(server, max_tokens=512).complete("s", "u", json_mode=False) == {"text": "ok"}
        assert server.bodies[0]["max_completion_tokens"] == 512 and "max_tokens" not in server.bodies[0]

    @pytest.mark.asyncio
    async def test_page_images_to_openai_use_the_new_name(self):
        server = OpenAI()
        await _handler(server, max_tokens=900).vision_complete("s", images=[b"page"], json_mode=False)
        assert server.bodies[0]["max_completion_tokens"] == 900 and "max_tokens" not in server.bodies[0]

    @pytest.mark.asyncio
    async def test_a_whole_pdf_to_openai_uses_the_new_name(self):
        server = OpenAI()
        await _handler(server, max_tokens=900).vision_complete("s", pdf_bytes=b"%PDF", json_mode=False)
        assert server.bodies[0]["max_completion_tokens"] == 900 and "max_tokens" not in server.bodies[0]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("api_base", ["http://lmstudio:1234/v1", "https://openrouter.ai/api/v1", ""])
    async def test_other_servers_keep_the_old_name(self, api_base):
        server = OpenAI()
        handler = _handler(server, model="local", api_base=api_base or "http://x", max_tokens=512)
        handler.api_base = api_base
        await handler.complete("s", "u", json_mode=False)
        assert server.bodies[0]["max_tokens"] == 512 and "max_completion_tokens" not in server.bodies[0]

    @pytest.mark.asyncio
    async def test_the_decision_asks_openai_for_one_token_under_the_new_name(self):
        server = OpenAI()
        adapter = OpenAILettersAdapter(_handler(server, model="gpt-4.1-mini"), PROMPT)
        (r,) = await adapter.score_rounds("t", "Q?", ASK, DESC)
        body = server.bodies[0]
        assert body["max_completion_tokens"] == 1 and "max_tokens" not in body
        assert "reasoning_effort" not in body and r.probs[0] > 0.99


class TestTheReasoningSwitch:
    @pytest.mark.asyncio
    async def test_switched_on_the_decision_turns_reasoning_off(self):
        server = OpenAI()
        adapter = OpenAILettersAdapter(_handler(server, reasoning_effort="none"), PROMPT)
        (r,) = await adapter.score_rounds("t", "Q?", ASK, DESC)
        assert server.bodies[0]["reasoning_effort"] == "none" and r.probs[0] > 0.99

    @pytest.mark.asyncio
    async def test_without_it_a_reasoning_model_cannot_decide(self):
        adapter = OpenAILettersAdapter(_handler(OpenAI()), PROMPT)
        with pytest.raises(DecisionUnsupported) as info:
            await adapter.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.reason == "unsupported_parameter" and "logprobs" in info.value.detail

    @pytest.mark.asyncio
    async def test_a_model_that_does_not_know_it_falls_back_to_the_text_prompt(self):
        # Left an error, this would count against the provider and stop the run.
        adapter = OpenAILettersAdapter(_handler(OpenAI(), model="gpt-4.1-mini", reasoning_effort="none"), PROMPT)
        with pytest.raises(DecisionUnsupported) as info:
            await adapter.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.reason == "unsupported_parameter" and "reasoning_effort" in info.value.detail

    @pytest.mark.asyncio
    async def test_a_retired_model_stays_an_error(self):
        adapter = OpenAILettersAdapter(_handler(OpenAI(), model="gpt-4.1-nano"), PROMPT)
        with pytest.raises(LLMHttpError) as info:
            await adapter.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.status_code == 404


@pytest.fixture
def settings(client):
    keys = ["llm_provider", "llm_model", "llm_api_base", "llm_provider_decision", "llm_model_decision",
            "llm_api_base_decision", "decision_reasoning_off"]

    def save(**values):
        for key, value in values.items():
            assert client.post("/api/config", json={"key": key, "value": value}).status_code == 200

    yield save
    for key in keys:
        client.delete(f"/api/config/{key}")
    DecisionServiceManager._service = None


async def _prompt(field):
    return PROMPT


def _probe(client, server):
    """POST /test-decision on the saved settings, with OpenAI and Paperless faked."""
    service = client.portal.call(DecisionService.from_config)
    service._prompt_loader = _prompt
    service._handler._client = httpx.AsyncClient(base_url=OPENAI, transport=httpx.MockTransport(server))
    DecisionServiceManager._service = service
    return client.post("/api/config/test-decision").json()


class TestTheSwitchInTheSettings:
    def test_saved_it_reaches_the_request(self, client, settings):
        settings(llm_provider="openai", llm_api_base=OPENAI, llm_model="gpt-6-luna", decision_reasoning_off="true")
        server = OpenAI()
        body = _probe(client, server)
        assert server.bodies[0]["reasoning_effort"] == "none" and server.bodies[0]["max_completion_tokens"] == 1
        assert (body["success"], body["method"], body["choice"], body["hint"]) == (
            True, "openai_letters", "Stadtwerke Saarbrücken", None)

    def test_saving_it_drops_the_service(self, client, settings):
        settings(llm_provider="openai", llm_api_base=OPENAI, llm_model="gpt-6-luna")
        service = client.portal.call(DecisionService.from_config)
        DecisionServiceManager._service = service
        settings(decision_reasoning_off="true")
        assert DecisionServiceManager._service is None and service.is_closed

    def test_an_own_openai_connection_takes_it_too(self, client, settings):
        settings(llm_provider="ollama", llm_provider_decision="openai", llm_api_base_decision=OPENAI,
                 llm_model_decision="gpt-6-luna", decision_reasoning_off="true")
        assert client.portal.call(DecisionService.from_config)._handler.reasoning_effort == "none"

    @pytest.mark.parametrize("provider", ["ollama", "openrouter", "grok"])
    def test_other_providers_never_get_it(self, client, settings, provider):
        settings(llm_provider=provider, llm_api_base="http://x", llm_model="m", decision_reasoning_off="true")
        assert client.portal.call(DecisionService.from_config)._handler.reasoning_effort is None

    def test_off_is_the_default(self, client, settings):
        settings(llm_provider="openai", llm_api_base=OPENAI, llm_model="gpt-4.1-mini")
        server = OpenAI()
        body = _probe(client, server)
        assert "reasoning_effort" not in server.bodies[0] and body["success"] is True


class TestTheTestPointsAtTheSwitch:
    def test_a_reasoning_model_with_the_switch_off(self, client, settings):
        settings(llm_provider="openai", llm_api_base=OPENAI, llm_model="gpt-6-luna")
        body = _probe(client, OpenAI())
        assert (body["success"], body["fallback_reason"], body["hint"]) == (
            False, "unsupported_parameter", "reasoning_off_needed")

    def test_an_older_model_with_the_switch_on(self, client, settings):
        settings(llm_provider="openai", llm_api_base=OPENAI, llm_model="gpt-4.1-mini", decision_reasoning_off="true")
        body = _probe(client, OpenAI())
        assert (body["success"], body["fallback_reason"], body["hint"]) == (
            False, "unsupported_parameter", "reasoning_off_refused")

    def test_a_local_server_without_probabilities_gets_no_hint(self, client, settings):
        settings(llm_provider="openai", llm_api_base="http://lmstudio:1234/v1", llm_model="local")

        def no_logprobs(request):
            return httpx.Response(200, json={"choices": [{"message": {"content": "A"}, "logprobs": None}]})

        body = _probe(client, no_logprobs)
        assert (body["fallback_reason"], body["hint"]) == ("no_logprobs", None)

    def test_a_refusal_of_something_else_leaves_the_switch_alone(self, client, settings):
        settings(llm_provider="openai", llm_api_base=OPENAI, llm_model="gpt-6-luna", decision_reasoning_off="true")

        def no_logprobs_at_all(request):
            return httpx.Response(400, json=LOGPROBS_REFUSED)

        body = _probe(client, no_logprobs_at_all)
        assert (body["fallback_reason"], body["hint"]) == ("unsupported_parameter", None)

    def test_a_fallback_that_never_asked_openai_gets_no_hint(self, client, settings):
        settings(llm_provider="openai", llm_api_base=OPENAI, llm_model="gpt-6-luna")
        service = client.portal.call(DecisionService.from_config)
        service._prompt_loader = None
        DecisionServiceManager._service = service
        body = client.post("/api/config/test-decision").json()
        assert (body["fallback_reason"], body["hint"]) == ("prompt_inactive", None)

    def test_a_retired_model_is_an_error_without_a_hint(self, client, settings):
        settings(llm_provider="openai", llm_api_base=OPENAI, llm_model="gpt-4.1-nano")
        body = _probe(client, OpenAI())
        assert body["success"] is False and "deprecated" in body["message"] and "hint" not in body
