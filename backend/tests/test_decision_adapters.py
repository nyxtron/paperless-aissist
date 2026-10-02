"""Each adapter's exact request and how it reads the answer, on captured bodies."""

import json

import httpx
import pytest

from app.exceptions import LLMHttpError, LLMUnavailableError
from app.services.decision.adapters import (
    DecisionSkipped,
    DecisionUnsupported,
    OllamaLettersAdapter,
    OllamaNimbleAdapter,
    OllamaSystemOneAdapter,
    OpenAILettersAdapter,
    classify_http_error,
    pick_adapter,
)
from app.services.decision.formats import NONE_LABEL, NONE_DESCRIPTION
from app.services.llm_handler import LLMHandler

PROMPT = {"system_prompt": "Answer with the letter.", "user_template": "Doc:\n{content}\n{question}\n{options}\nLetter only."}
OLLAMA_REPLY = {"message": {"content": "B"}, "done_reason": "length", "prompt_eval_count": 180,
                "logprobs": [{"token": "B", "logprob": 0.0, "top_logprobs": [
                    {"token": "B", "logprob": 0.0}, {"token": "A", "logprob": -8.0}, {"token": "C", "logprob": -9.0}]}]}
OPENAI_REPLY = {"choices": [{"finish_reason": "length", "message": {"content": "B"}, "logprobs": {"content": [
    {"token": "B", "logprob": 0.0, "top_logprobs": [{"token": "B", "logprob": 0.0}, {"token": "A", "logprob": -8.0}]}]}}]}


class Recorder:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request):
        self.requests.append((request.url.path, json.loads(request.content)))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        status, body = reply
        return httpx.Response(status, json=body) if isinstance(body, dict) else httpx.Response(status, text=body)


def _handler(recorder, provider="ollama", num_ctx=None):
    h = LLMHandler(provider=provider, model="m", api_base="http://llm.test", num_ctx=num_ctx)
    h._client = httpx.AsyncClient(base_url="http://llm.test", transport=httpx.MockTransport(recorder))
    return h


ASK = [("c0", ["Amazon", "Telekom", NONE_LABEL])]
DESC = {NONE_LABEL: NONE_DESCRIPTION}


class TestOllamaLetters:
    @pytest.mark.asyncio
    async def test_the_request_and_the_answer(self):
        rec = Recorder([(200, OLLAMA_REPLY)])
        a = OllamaLettersAdapter(_handler(rec, num_ctx=8192), PROMPT)
        (r,) = await a.score_rounds("the text", "Q?", ASK, DESC)
        path, body = rec.requests[0]
        assert path == "/api/chat"
        assert body["think"] is False and body["logprobs"] is True and body["top_logprobs"] == 20
        assert body["options"] == {"temperature": 0, "num_predict": 1, "num_ctx": 8192}
        assert body["messages"][0] == {"role": "system", "content": "Answer with the letter."}
        assert body["messages"][1]["content"] == "Doc:\nthe text\nQ?\nA: Amazon\nB: Telekom\nC: None of these\nLetter only."
        assert r.probs[1] > 0.99 and set(r.probs) == {0, 1, 2} and r.input_tokens == 180
        assert "the text" in r.full and "<document text, 8 chars>" in r.rendered and "the text" not in r.rendered
        assert a.requests == 1

    @pytest.mark.asyncio
    async def test_no_logprobs_in_a_200_is_unsupported(self):
        a = OllamaLettersAdapter(_handler(Recorder([(200, {"message": {"content": "B"}})])), PROMPT)
        with pytest.raises(DecisionUnsupported) as info:
            await a.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.reason == "no_logprobs"

    @pytest.mark.asyncio
    async def test_a_refused_parameter_is_unsupported(self):
        body = {"error": "json: unknown field \"logprobs\""}
        a = OllamaLettersAdapter(_handler(Recorder([(400, body)])), PROMPT)
        with pytest.raises(DecisionUnsupported) as info:
            await a.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.reason == "unsupported_parameter"

    @pytest.mark.asyncio
    async def test_a_wrong_key_stays_a_provider_failure(self):
        a = OllamaLettersAdapter(_handler(Recorder([(401, "no")])), PROMPT)
        with pytest.raises(LLMHttpError):
            await a.score_rounds("t", "Q?", ASK, DESC)

    @pytest.mark.asyncio
    async def test_a_down_provider_stays_retryable(self):
        a = OllamaLettersAdapter(_handler(Recorder([(503, "busy")])), PROMPT)
        with pytest.raises(LLMUnavailableError):
            await a.score_rounds("t", "Q?", ASK, DESC)


class TestOpenAILetters:
    @pytest.mark.asyncio
    async def test_the_request_and_the_answer(self):
        rec = Recorder([(200, OPENAI_REPLY)])
        a = OpenAILettersAdapter(_handler(rec, provider="openrouter"), PROMPT)
        (r,) = await a.score_rounds("t", "Q?", ASK, DESC)
        path, body = rec.requests[0]
        assert path == "/chat/completions"
        assert body["temperature"] == 0 and body["max_tokens"] == 1 and body["logprobs"] is True and body["top_logprobs"] == 20
        assert body["provider"] == {"require_parameters": True}
        assert r.probs[1] > 0.99

    @pytest.mark.asyncio
    async def test_openai_itself_sends_no_provider_block(self):
        rec = Recorder([(200, OPENAI_REPLY)])
        await OpenAILettersAdapter(_handler(rec, provider="openai"), PROMPT).score_rounds("t", "Q?", ASK, DESC)
        assert "provider" not in rec.requests[0][1]

    @pytest.mark.asyncio
    async def test_a_server_ignoring_logprobs_is_unsupported(self):
        reply = {"choices": [{"finish_reason": "length", "message": {"content": "B"}, "logprobs": None}]}
        a = OpenAILettersAdapter(_handler(Recorder([(200, reply)]), provider="openai"), PROMPT)
        with pytest.raises(DecisionUnsupported) as info:
            await a.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.reason == "no_logprobs"

    @pytest.mark.asyncio
    async def test_a_reasoning_model_refusing_temperature_is_unsupported(self):
        body = {"error": {"message": "Unsupported value: 'temperature' does not support 0 with this model.",
                          "type": "invalid_request_error", "param": "temperature", "code": "unsupported_value"}}
        a = OpenAILettersAdapter(_handler(Recorder([(400, body)]), provider="openai"), PROMPT)
        with pytest.raises(DecisionUnsupported) as info:
            await a.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.reason == "unsupported_parameter"

    @pytest.mark.asyncio
    async def test_openrouter_without_an_endpoint_is_unsupported(self):
        body = {"error": {"message": "No endpoints found that can handle the requested parameters.", "code": 404}}
        a = OpenAILettersAdapter(_handler(Recorder([(404, body)]), provider="openrouter"), PROMPT)
        with pytest.raises(DecisionUnsupported) as info:
            await a.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.reason == "no_logprobs"


class TestNimble:
    @pytest.mark.asyncio
    async def test_only_the_user_message_is_sent(self):
        rec = Recorder([(200, OLLAMA_REPLY)])
        a = OllamaNimbleAdapter(_handler(rec))
        (r,) = await a.score_rounds("the text", "Q?", ASK, DESC)
        path, body = rec.requests[0]
        assert path == "/api/chat" and body["think"] is False
        assert body["logprobs"] is True and body["top_logprobs"] == 20
        assert body["options"] == {"temperature": 0, "num_predict": 1}
        assert [m["role"] for m in body["messages"]] == ["user"]
        payload, _, tail = body["messages"][0]["content"].partition("\n\nRequested field: ")
        assert tail == '"field"' and json.loads(payload)["context"] == "the text"
        assert r.probs[1] > 0.99
        assert "<document text, 8 chars>" in r.rendered and "the text" not in r.rendered and "the text" in r.full


class TestSystemOne:
    @pytest.mark.asyncio
    async def test_a_chunk_round_goes_in_one_request(self):
        reply = {"answers": {"c0": {"choice": "Amazon", "probabilities": {"Amazon": 0.9, "Telekom": 0.05, NONE_LABEL: 0.05}},
                             "c1": {"choice": NONE_LABEL, "probabilities": {"Zalando": 0.2, NONE_LABEL: 0.8}}},
                 "usage": {"input_tokens": 500, "output_tokens": 2}}
        rec = Recorder([(200, reply)])
        a = OllamaSystemOneAdapter(_handler(rec))
        asks = [("c0", ["Amazon", "Telekom", NONE_LABEL]), ("c1", ["Zalando", NONE_LABEL])]
        r0, r1 = await a.score_rounds("the text", "Q?", asks, DESC)
        path, body = rec.requests[0]
        assert path == "/v1/systemone" and body["state"] == "the text" and "options" not in body
        assert body["questions"]["c0"] == {"type": "choice", "instructions": "Q?",
                                           "criteria": {"Amazon": None, "Telekom": None, NONE_LABEL: NONE_DESCRIPTION}}
        assert r0.probs == {0: 0.9, 1: 0.05, 2: 0.05} and r0.mass is None and r0.input_tokens == 500
        assert r1.probs == {0: 0.2, 1: 0.8} and a.requests == 1
        assert "<document text, 8 chars>" in r0.rendered and "the text" not in r0.rendered
        assert json.loads(r0.full)["state"] == "the text"

    @pytest.mark.asyncio
    async def test_duplicate_names_map_back_by_position(self):
        reply = {"answers": {"c0": {"choice": "Telekom (2)", "probabilities": {"Telekom": 0.1, "Telekom (2)": 0.85, NONE_LABEL: 0.05}}},
                 "usage": {"input_tokens": 1}}
        a = OllamaSystemOneAdapter(_handler(Recorder([(200, reply)])))
        (r,) = await a.score_rounds("t", "Q?", [("c0", ["Telekom", "Telekom", NONE_LABEL])], DESC)
        assert r.probs == {0: 0.1, 1: 0.85, 2: 0.05}

    @pytest.mark.asyncio
    async def test_a_round_over_the_context_is_retried_one_by_one(self):
        too_long = {"error": "prompt 0 has 9000 tokens; expected 1–8194 (input is never truncated)"}
        ok = lambda name, label: (200, {"answers": {name: {"choice": label, "probabilities": {label: 0.9, NONE_LABEL: 0.1}}}, "usage": {"input_tokens": 1}})  # noqa: E731
        rec = Recorder([(400, too_long), ok("c0", "Amazon"), ok("c1", "Zalando")])
        a = OllamaSystemOneAdapter(_handler(rec))
        r0, r1 = await a.score_rounds("t", "Q?", [("c0", ["Amazon", NONE_LABEL]), ("c1", ["Zalando", NONE_LABEL])], DESC)
        assert [set(b["questions"]) for _, b in rec.requests] == [{"c0", "c1"}, {"c0"}, {"c1"}]
        assert r0.probs[0] == 0.9 and r1.probs[0] == 0.9

    @pytest.mark.asyncio
    async def test_a_single_question_over_the_context_is_skipped(self):
        too_long = {"error": "prompt 0 has 9000 tokens; expected 1–8194 (input is never truncated)"}
        a = OllamaSystemOneAdapter(_handler(Recorder([(400, too_long)])))
        with pytest.raises(DecisionSkipped) as info:
            await a.score_rounds("t", "Q?", [("c0", ["Amazon", NONE_LABEL])], DESC)
        assert info.value.reason == "context_exceeded"

    @pytest.mark.asyncio
    async def test_a_body_over_the_byte_budget_is_split_before_sending(self):
        ok = lambda name: (200, {"answers": {name: {"choice": NONE_LABEL, "probabilities": {"X": 0.1, NONE_LABEL: 0.9}}}, "usage": {"input_tokens": 1}})  # noqa: E731
        rec = Recorder([ok("c0"), ok("c1")])
        a = OllamaSystemOneAdapter(_handler(rec))
        await a.score_rounds("x" * 30_000, "Q?", [("c0", ["X", NONE_LABEL]), ("c1", ["X", NONE_LABEL])], DESC)
        assert len(rec.requests) == 2

    @pytest.mark.asyncio
    async def test_a_configured_window_does_not_change_the_budget(self):
        ok = lambda name: (200, {"answers": {name: {"choice": NONE_LABEL, "probabilities": {"X": 0.1, NONE_LABEL: 0.9}}}, "usage": {"input_tokens": 1}})  # noqa: E731
        rec = Recorder([ok("c0"), ok("c1")])
        a = OllamaSystemOneAdapter(_handler(rec, num_ctx=65536))
        await a.score_rounds("x" * 30_000, "Q?", [("c0", ["X", NONE_LABEL]), ("c1", ["X", NONE_LABEL])], DESC)
        assert len(rec.requests) == 2

    @pytest.mark.asyncio
    async def test_an_option_spelled_like_the_sentinel_maps_back(self):
        reply = {"answers": {"c0": {"choice": "None of these (2)", "probabilities": {"None of these (2)": 0.7, "Telekom": 0.2, NONE_LABEL: 0.1}}},
                 "usage": {"input_tokens": 1}}
        a = OllamaSystemOneAdapter(_handler(Recorder([(200, reply)])))
        (r,) = await a.score_rounds("t", "Q?", [("c0", ["None of these", "Telekom", NONE_LABEL])], DESC)
        assert r.probs == {0: 0.7, 1: 0.2, 2: 0.1}

    @pytest.mark.asyncio
    async def test_the_route_missing_is_unsupported_but_a_missing_model_is_not(self):
        a = OllamaSystemOneAdapter(_handler(Recorder([(404, "404 page not found")])))
        with pytest.raises(DecisionUnsupported) as info:
            await a.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.reason == "route_missing"
        a = OllamaSystemOneAdapter(_handler(Recorder([(404, {"error": 'model "nimble" not found, try pulling it first'})])))
        with pytest.raises(LLMHttpError):
            await a.score_rounds("t", "Q?", ASK, DESC)

    @pytest.mark.asyncio
    async def test_a_model_system_one_cannot_run_is_unsupported(self):
        body = {"error": 'model "qwen2.5:7b" is not supported by System One; use a local Nimble or Tev GGUF model'}
        a = OllamaSystemOneAdapter(_handler(Recorder([(400, body)])))
        with pytest.raises(DecisionUnsupported) as info:
            await a.score_rounds("t", "Q?", ASK, DESC)
        assert info.value.reason == "format_unsupported"


class TestClassify:
    def test_the_table(self):
        e = lambda s, b: LLMHttpError("x", status_code=s, body=b)  # noqa: E731
        assert classify_http_error(e(400, '{"error":{"code":"unsupported_parameter","param":"logprobs"}}')) == ("unsupported_parameter", True)
        assert classify_http_error(e(400, "max_tokens is not supported with this model")) == ("unsupported_parameter", True)
        assert classify_http_error(e(404, "No endpoints found that can handle the requested parameters")) == ("no_logprobs", True)
        assert classify_http_error(e(400, "is not supported by System One")) == ("format_unsupported", True)
        assert classify_http_error(e(404, "404 page not found")) == ("route_missing", True)
        assert classify_http_error(e(400, "prompt 0 has 9000 tokens; expected 1–8194 (input is never truncated)")) == ("context_exceeded", False)
        assert classify_http_error(e(413, "request body must not exceed 64 KiB")) == ("context_exceeded", False)
        assert classify_http_error(e(401, "Incorrect API key")) is None
        assert classify_http_error(e(404, '{"error":"model \\"x\\" not found"}')) is None


class TestPickAdapter:
    def test_the_table(self):
        assert pick_adapter("ollama", "nimble:latest", "auto") == (OllamaNimbleAdapter, None)
        assert pick_adapter("ollama", "qwen2.5:7b", "auto") == (OllamaLettersAdapter, None)
        assert pick_adapter("ollama", "nimble", "letters") == (OllamaLettersAdapter, None)
        assert pick_adapter("ollama", "qwen2.5:7b", "systemone") == (OllamaSystemOneAdapter, None)
        assert pick_adapter("openai", "gpt-4o-mini", "auto") == (OpenAILettersAdapter, None)
        assert pick_adapter("openrouter", "x", "nimble") == (None, "format_unsupported")
        assert pick_adapter("grok", "grok-3", "auto") == (None, "provider_unsupported")
        assert pick_adapter("grok", "grok-3", "systemone") == (None, "format_unsupported")
