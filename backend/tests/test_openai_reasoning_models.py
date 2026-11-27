"""OpenAI's gpt-5 and gpt-6 models take other parameters than the older ones.

They refuse max_tokens, and with reasoning on they refuse logprobs and a
temperature of 0, so decision mode has a switch that turns reasoning off. With
it off gpt-6-luna shows five candidates at most, lists only the ones that
carry weight and answers nothing below four output tokens. Text and page
requests it turns down over their temperature go out again without one. The
bodies below are the ones from issue #59 and from api.openai.com on 2026-11-20.
"""

import functools
import json
import logging
import math

import httpx
import pytest

from app.exceptions import LLMError, LLMHttpError
from app.services.decision import DecisionService, DecisionServiceManager
from app.services.decision.adapters import DecisionUnsupported, OpenAILettersAdapter, letter_probs
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
TEMPERATURE_REFUSED = {"error": {
    "message": "Unsupported value: 'temperature' does not support 0 with this model. Only the default (1) value is supported.",
    "type": "invalid_request_error", "param": "temperature", "code": "unsupported_value"}}
LOGPROBS_REFUSED = {"error": {
    "message": "Unsupported parameter: 'logprobs' is not supported with this model.",
    "type": "invalid_request_error", "param": "logprobs", "code": "unsupported_parameter"}}
TOO_MANY_CANDIDATES = {"error": {
    "message": "Invalid value for 'top_logprobs': must be less than or equal to 5.",
    "type": "invalid_request_error", "param": "top_logprobs", "code": None}}
NO_ROOM = {"error": {
    "message": "Could not finish the message because max_tokens or model output limit was reached. Please try again with higher max_tokens.",
    "type": "invalid_request_error", "param": None, "code": None}}
REASONING_UNKNOWN = {"error": {
    "message": "Unrecognized request argument supplied: reasoning_effort",
    "type": "invalid_request_error", "param": None, "code": None}}
LETTER = {"choices": [{"finish_reason": "length", "message": {"content": "A"}, "logprobs": {"content": [
    {"token": "A", "logprob": -0.01, "top_logprobs": [{"token": "A", "logprob": -0.01}, {"token": "B", "logprob": -5.0}]}]}}],
    "usage": {"prompt_tokens": 60}}
# gpt-6-luna on a clear question: one candidate, the rest of the weight unseen.
LUNA_LETTER = {"choices": [{"finish_reason": "stop", "message": {"content": "A"}, "logprobs": {"content": [
    {"token": "A", "logprob": -0.0015239715576171875,
     "top_logprobs": [{"token": "A", "logprob": -0.0015239715576171875}]}]}}],
    "usage": {"prompt_tokens": 37, "completion_tokens": 4}}
LUNA_CUT_SHORT = {"choices": [{"finish_reason": "length", "message": {"content": ""},
                               "logprobs": {"content": [], "refusal": None}}]}
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
            if body.get("reasoning_effort") != "none":
                if body.get("temperature", 1) != 1:
                    return httpx.Response(400, json=TEMPERATURE_REFUSED)
                if body.get("logprobs"):
                    return httpx.Response(400, json=LOGPROBS_REFUSED)
            elif body.get("logprobs"):
                if body.get("top_logprobs", 0) > 5:
                    return httpx.Response(400, json=TOO_MANY_CANDIDATES)
                if body["max_completion_tokens"] < 3:
                    return httpx.Response(400, json=NO_ROOM)
                return httpx.Response(200, json=LUNA_CUT_SHORT if body["max_completion_tokens"] < 4 else LUNA_LETTER)
        elif "reasoning_effort" in body:
            return httpx.Response(400, json=REASONING_UNKNOWN)
        return httpx.Response(200, json=LETTER if body.get("logprobs") else TEXT)


def _handler(server, model="gpt-6-luna", api_base=OPENAI, **settings):
    handler = LLMHandler(provider="openai", model=model, api_base=api_base, **settings)
    handler._client = httpx.AsyncClient(base_url=api_base, transport=httpx.MockTransport(server))
    return handler


def _luna(server, **settings):
    """gpt-6-luna for text and pages; with reasoning on it only takes its default temperature."""
    return _handler(server, temperature=1.0, **settings)


class TestTheOutputLimitName:
    @pytest.mark.asyncio
    async def test_a_text_request_to_openai_uses_the_new_name(self):
        server = OpenAI()
        assert await _luna(server, max_tokens=512).complete("s", "u", json_mode=False) == {"text": "ok"}
        assert server.bodies[0]["max_completion_tokens"] == 512 and "max_tokens" not in server.bodies[0]

    @pytest.mark.asyncio
    async def test_page_images_to_openai_use_the_new_name(self):
        server = OpenAI()
        await _luna(server, max_tokens=900).vision_complete("s", images=[b"page"], json_mode=False)
        assert server.bodies[0]["max_completion_tokens"] == 900 and "max_tokens" not in server.bodies[0]

    @pytest.mark.asyncio
    async def test_a_whole_pdf_to_openai_uses_the_new_name(self):
        server = OpenAI()
        await _luna(server, max_tokens=900).vision_complete("s", pdf_bytes=b"%PDF", json_mode=False)
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
        assert body["top_logprobs"] == 20 and "reasoning_effort" not in body
        # Among the letters it showed, as before: 0.990 against 0.007.
        assert r.probs[0] == pytest.approx(0.9932, abs=1e-4)


class TestTheReasoningSwitch:
    @pytest.mark.asyncio
    async def test_switched_on_the_decision_turns_reasoning_off(self):
        server = OpenAI()
        adapter = OpenAILettersAdapter(_handler(server, reasoning_effort="none"), PROMPT)
        (r,) = await adapter.score_rounds("t", "Q?", ASK, DESC)
        assert server.bodies[0]["reasoning_effort"] == "none" and r.probs[0] > 0.99

    @pytest.mark.asyncio
    async def test_switched_on_it_asks_for_what_the_model_allows(self):
        # The stand-in refuses more than five candidates and less than four tokens.
        server = OpenAI()
        adapter = OpenAILettersAdapter(_handler(server, reasoning_effort="none"), PROMPT)
        await adapter.score_rounds("t", "Q?", ASK, DESC)
        body = server.bodies[0]
        assert (body["top_logprobs"], body["max_completion_tokens"], body["temperature"]) == (5, 16, 0)

    @pytest.mark.asyncio
    async def test_what_the_model_did_not_show_counts_against_the_letter(self):
        adapter = OpenAILettersAdapter(_handler(OpenAI(), reasoning_effort="none"), PROMPT)
        (r,) = await adapter.score_rounds("t", "Q?", ASK, DESC)
        assert r.probs == {0: pytest.approx(0.99848, abs=1e-5)} and r.mass == pytest.approx(0.99848, abs=1e-5)

    @pytest.mark.asyncio
    async def test_without_it_a_reasoning_model_cannot_decide(self):
        adapter = OpenAILettersAdapter(_handler(OpenAI()), PROMPT)
        with pytest.raises(DecisionUnsupported) as info:
            await adapter.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.reason == "unsupported_parameter" and "temperature" in info.value.detail

    @pytest.mark.asyncio
    async def test_an_answer_cut_before_the_letter_is_no_decision(self):
        def cut_short(request):
            return httpx.Response(200, json=LUNA_CUT_SHORT)

        adapter = OpenAILettersAdapter(_handler(cut_short, reasoning_effort="none"), PROMPT)
        with pytest.raises(DecisionUnsupported) as info:
            await adapter.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.reason == "no_logprobs"

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


def _sent_temperatures(server):
    return [b.get("temperature", "left out") for b in server.bodies]


class TestARefusedTemperature:
    @pytest.mark.asyncio
    async def test_a_text_request_goes_again_without_it(self):
        server = OpenAI()
        assert await _handler(server, max_tokens=512).complete("s", "u", json_mode=False) == {"text": "ok"}
        first, second = server.bodies
        assert first["temperature"] == 0.3 and second == {k: v for k, v in first.items() if k != "temperature"}

    @pytest.mark.asyncio
    async def test_after_the_refusal_it_is_left_out_straight_away(self):
        server = OpenAI()
        handler = _handler(server)
        await handler.complete("s", "u", json_mode=False)
        await handler.complete("s", "u", json_mode=False)
        assert _sent_temperatures(server) == [0.3, "left out", "left out"]

    @pytest.mark.asyncio
    async def test_a_handler_built_after_a_settings_save_still_knows(self):
        server = OpenAI()
        await _handler(server).complete("s", "u", json_mode=False)
        await _handler(server).complete("s", "u", json_mode=False)
        assert _sent_temperatures(server) == [0.3, "left out", "left out"]

    @pytest.mark.asyncio
    async def test_page_images_go_again_without_it(self):
        server = OpenAI()
        result = await _handler(server).vision_complete("s", images=[b"p1", b"p2"], json_mode=False)
        assert result == {"text": "ok\n\nok"}
        assert _sent_temperatures(server) == [0.3, "left out", "left out"]

    @pytest.mark.asyncio
    async def test_a_whole_pdf_goes_again_without_it(self):
        server = OpenAI()
        assert await _handler(server).vision_complete("s", pdf_bytes=b"%PDF", json_mode=False) == {"text": "ok"}
        assert _sent_temperatures(server) == [0.3, "left out"]

    @pytest.mark.asyncio
    async def test_a_model_that_takes_it_gets_it_as_set(self):
        server = OpenAI()
        await _handler(server, model="gpt-4.1-mini", temperature=0.2).complete("s", "u", json_mode=False)
        assert _sent_temperatures(server) == [0.2]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("model, api_base", [("gpt-4.1-mini", OPENAI), ("gpt-6-luna", "https://proxy.example/v1")])
    async def test_the_refusal_belongs_to_one_model_at_one_address(self, model, api_base):
        server = OpenAI()
        await _handler(server).complete("s", "u", json_mode=False)
        await _handler(server, model=model, api_base=api_base).complete("s", "u", json_mode=False)
        assert server.bodies[2]["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_a_refusal_of_something_else_is_not_sent_again(self):
        # LM Studio and the like get max_tokens, which gpt-6 refuses.
        server = OpenAI()
        handler = _handler(server, api_base="http://lmstudio:1234/v1", max_tokens=512)
        with pytest.raises(LLMError, match="max_tokens"):
            await handler.complete("s", "u", json_mode=False)
        assert len(server.bodies) == 1

    @pytest.mark.asyncio
    async def test_the_log_says_so_once(self, caplog):
        handler = _handler(OpenAI())
        with caplog.at_level(logging.WARNING, logger="app.services.llm_handler"):
            await handler.complete("s", "u", json_mode=False)
            await handler.complete("s", "u", json_mode=False)
        said = [r.getMessage() for r in caplog.records if "refused a temperature" in r.getMessage()]
        assert len(said) == 1 and "gpt-6-luna" in said[0] and "Temperature 1" in said[0]

    @pytest.mark.asyncio
    async def test_the_decision_keeps_its_own(self):
        # With reasoning off luna takes a temperature of 0, and the letters rely on it.
        server = OpenAI()
        handler = _handler(server, reasoning_effort="none")
        await handler.complete("s", "u", json_mode=False)
        await OpenAILettersAdapter(handler, PROMPT).score_rounds("t", "Q?", ASK, DESC)
        assert _sent_temperatures(server) == [0.3, "left out", 0]


def _top(**weights):
    return [{"token": token, "logprob": math.log(p)} for token, p in weights.items()]


class TestCandidatesLeftOut:
    def test_the_unseen_weight_goes_into_the_denominator(self):
        probs, mass = letter_probs(_top(A=0.6, B=0.05), 20, partial=True)
        assert probs == {0: pytest.approx(0.6), 1: pytest.approx(0.05)} and mass == pytest.approx(0.65)

    def test_without_it_only_the_shown_letters_count(self):
        probs, mass = letter_probs(_top(A=0.6, B=0.05), 20)
        assert probs[0] == pytest.approx(0.6 / 0.65) and mass == pytest.approx(0.65)

    def test_a_shown_word_is_neither_letter_nor_unseen(self):
        probs, _ = letter_probs(_top(A=0.6, The=0.3), 20, partial=True)
        assert probs == {0: pytest.approx(0.6 / 0.7)}

    def test_nothing_unseen_changes_nothing(self):
        top = _top(A=0.9, B=0.1)
        assert letter_probs(top, 20, partial=True) == letter_probs(top, 20)

    def test_weights_that_add_up_to_more_than_one_are_not_scaled_down(self):
        # Rounded logprobs can add up to a little over one.
        probs, _ = letter_probs([{"token": "A", "logprob": 0.0}, {"token": "B", "logprob": -6.0}], 20, partial=True)
        assert probs[0] == pytest.approx(1 / (1 + math.exp(-6.0)))


@pytest.fixture
def settings(client):
    keys = ["llm_provider", "llm_model", "llm_api_base", "llm_provider_decision", "llm_model_decision",
            "llm_api_base_decision", "decision_reasoning_off", "llm_temperature", "llm_provider_vision",
            "llm_model_vision", "llm_api_base_vision", "llm_temperature_vision"]

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
        sent = server.bodies[0]
        assert (sent["reasoning_effort"], sent["max_completion_tokens"], sent["top_logprobs"]) == ("none", 16, 5)
        assert (body["success"], body["method"], body["choice"], body["hint"]) == (
            True, "openai_letters", "Stadtwerke Saarbrücken", None)
        assert body["probability"] == pytest.approx(0.99848, abs=1e-5)

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
        sent = server.bodies[0]
        assert "reasoning_effort" not in sent and (sent["max_completion_tokens"], sent["top_logprobs"]) == (1, 20)
        assert body["success"] is True and body["probability"] == pytest.approx(0.9932, abs=1e-4)


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


def _from_settings(client, server, for_vision=False):
    handler = client.portal.call(LLMHandler.from_config, for_vision)
    handler._client = httpx.AsyncClient(base_url=OPENAI, transport=httpx.MockTransport(server))
    return handler


class TestLunaAsTheMainModel:
    def test_the_saved_temperature_is_tried_first(self, client, settings):
        settings(llm_provider="openai", llm_api_base=OPENAI, llm_model="gpt-6-luna", llm_temperature="0.2")
        server = OpenAI()
        handler = _from_settings(client, server)
        assert client.portal.call(handler.complete, "s", "u", False) == {"text": "ok"}
        assert _sent_temperatures(server) == [0.2, "left out"]

    def test_pages_for_its_own_vision_model_too(self, client, settings):
        settings(llm_provider="ollama", llm_provider_vision="openai", llm_api_base_vision=OPENAI,
                 llm_model_vision="gpt-6-luna", llm_temperature_vision="0.1")
        server = OpenAI()
        handler = _from_settings(client, server, for_vision=True)
        read = functools.partial(handler.vision_complete, "s", images=[b"p1"], json_mode=False)
        assert client.portal.call(read) == {"text": "ok"}
        assert _sent_temperatures(server) == [0.1, "left out"]
