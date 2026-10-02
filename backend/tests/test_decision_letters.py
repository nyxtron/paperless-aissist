"""Letters in, a decision out: the parser on captured replies and the rounds
on a fake adapter, with the rules the 60-document measurement was scored by."""

import pytest

from app.services.decision.adapters import (
    Adapter,
    DecisionSkipped,
    DecisionUnsupported,
    RoundResult,
    letter_probs,
)
from app.services.decision.formats import NONE_LABEL
from app.services.decision.service import DecisionService, chunks
from app.services.llm_handler import LLMHandler

# Captured from Ollama 0.35.0, qwen2.5:7b, four options A..D (logprobs rounded).
OLLAMA_TOP = [
    {"token": "B", "logprob": 0.0}, {"token": "D", "logprob": -19.48}, {"token": "A", "logprob": -20.58},
    {"token": "C", "logprob": -23.52}, {"token": "*B", "logprob": -24.52}, {"token": "Б", "logprob": -25.32},
    {"token": "Ｂ", "logprob": -25.66}, {"token": "_B", "logprob": -25.79}, {"token": "S", "logprob": -26.05},
    {"token": "E", "logprob": -26.27},
]


class TestLetterProbs:
    def test_the_captured_ollama_reply(self):
        probs, mass = letter_probs(OLLAMA_TOP, 4)
        assert probs[1] > 0.9999 and set(probs) == {0, 1, 2, 3}
        assert mass == pytest.approx(1.0, abs=1e-6)

    def test_a_leading_space_is_stripped_and_the_first_occurrence_wins(self):
        probs, mass = letter_probs([{"token": " B", "logprob": -0.5}, {"token": "B", "logprob": -0.1},
                                    {"token": "A", "logprob": -2.0}], 2)
        assert probs[1] == pytest.approx(0.8176, abs=1e-3)
        assert mass == pytest.approx(0.6065 + 0.1353, abs=1e-3)

    def test_a_letter_with_punctuation_does_not_count(self):
        probs, mass = letter_probs([{"token": "B.", "logprob": -0.1}, {"token": "B:", "logprob": -0.2}], 2)
        assert probs == {} and mass == 0.0

    def test_blank_tokens_are_skipped(self):
        probs, _ = letter_probs([{"token": "", "logprob": -0.1}, {"token": "  ", "logprob": -0.2},
                                 {"token": "A", "logprob": -1.0}], 2)
        assert set(probs) == {0}

    def test_letters_beyond_n_are_ignored(self):
        probs, _ = letter_probs([{"token": "C", "logprob": -0.1}, {"token": "A", "logprob": -1.0}], 2)
        assert set(probs) == {0}


class TestChunks:
    def test_the_measured_sizes(self):
        assert [len(c) for c in chunks(list(range(112)), 19)] == [19, 19, 19, 19, 19, 17]
        assert [len(c) for c in chunks(list(range(30)), 19)] == [15, 15]
        assert [len(c) for c in chunks(list(range(30)), 25)] == [15, 15]
        assert [len(c) for c in chunks(list(range(19)), 19)] == [19]


class FakeAdapter(Adapter):
    """Answers from a script: {round name: {label: p}}; mass per round optional."""

    method = "fake"
    uses_prompt = False

    def __init__(self, handler, prompt=None, script=None, masses=None, max_options=20):
        super().__init__(handler, prompt)
        self.script = script or {}
        self.masses = masses or {}
        self.max_options = max_options
        self.asked: list[tuple[str, list[str]]] = []

    async def _score_one(self, text, question, name, labels, descriptions):
        self.asked.append((name, list(labels)))
        self.requests += 1
        answer = self.script[name]
        if isinstance(answer, list):  # one answer per visit of this round name
            answer = answer.pop(0)
        mass = self.masses.get(name, 1.0)
        if isinstance(mass, list):
            mass = mass.pop(0)
        if answer == "no_letters":
            return RoundResult(probs={}, mass=0.0, rendered=f"<{name}>", full=f"<{name}:{text}>", input_tokens=1)
        if answer == "unsupported":
            raise DecisionUnsupported("no_logprobs", "200 without logprobs")
        probs = {labels.index(label): p for label, p in answer.items()}
        return RoundResult(probs=probs, mass=mass, rendered=f"<{name}>",
                           full=f"<{name}:{text}>", input_tokens=1)


def _service(script, masses=None, max_options=20):
    handler = LLMHandler(provider="ollama", model="fake", api_base="http://x")

    class Cls(FakeAdapter):
        def __init__(self, h, p=None):
            super().__init__(h, p, script, masses, max_options)

    return DecisionService(handler, Cls, None, None)


NAMES = [f"Firma {i:03d}" for i in range(40)]


async def _decide(service, options, **kw):
    return await service.decide("text", "correspondent", options, question="Q?", threshold=0.9, **kw)


class TestRounds:
    @pytest.mark.asyncio
    async def test_nineteen_names_need_one_round(self):
        s = _service({"c0": {"Firma 003": 0.97, NONE_LABEL: 0.01}})
        d = await _decide(s, NAMES[:19])
        assert (d.index, d.choice, d.probability, d.requests) == (3, "Firma 003", 0.97, 1)
        assert s._adapter_calls[0].asked[0][1][-1] == NONE_LABEL and len(s._adapter_calls[0].asked[0][1]) == 20

    @pytest.mark.asyncio
    async def test_one_chunk_winner_keeps_its_probability(self):
        s = _service({"c0": {"Firma 003": 0.95}, "c1": {NONE_LABEL: 0.8}, "c2": {NONE_LABEL: 0.7}})
        d = await _decide(s, NAMES[:40])
        assert (d.index, d.probability, d.requests, d.review_reason) == (3, 0.95, 3, None)

    @pytest.mark.asyncio
    async def test_no_winner_is_none_with_the_lowest_none_probability(self):
        s = _service({"c0": {NONE_LABEL: 0.95}, "c1": {NONE_LABEL: 0.6}, "c2": {NONE_LABEL: 0.99}})
        d = await _decide(s, NAMES[:40])
        assert (d.index, d.choice, d.probability) == (None, NONE_LABEL, 0.6)
        assert d.rendered == "<c1>"

    @pytest.mark.asyncio
    async def test_several_winners_go_to_a_final_round(self):
        s = _service({"c0": {"Firma 003": 0.6}, "c1": {"Firma 020": 0.99}, "c2": {NONE_LABEL: 0.9},
                      "final": {"Firma 020": 0.97, "Firma 003": 0.02}})
        d = await _decide(s, NAMES[:40])
        assert (d.index, d.probability, d.requests) == (20, 0.97, 4)
        assert s._adapter_calls[0].asked[-1] == ("final", ["Firma 003", "Firma 020", NONE_LABEL])

    @pytest.mark.asyncio
    async def test_a_near_tie_in_a_chunk_caps_the_final_probability(self):
        s = _service({"c0": {"Firma 003": 0.45, "Firma 004": 0.44}, "c1": {"Firma 020": 0.8},
                      "c2": {NONE_LABEL: 0.9}, "final": {"Firma 003": 0.97}})
        d = await _decide(s, NAMES[:40])
        assert (d.index, d.probability) == (3, 0.45)

    @pytest.mark.asyncio
    async def test_a_final_round_that_picks_none_is_a_review(self):
        s = _service({"c0": {"Firma 003": 0.6}, "c1": {"Firma 020": 0.7}, "c2": {NONE_LABEL: 0.9},
                      "final": {NONE_LABEL: 0.8}})
        d = await _decide(s, NAMES[:40])
        assert (d.review_reason, d.choice, d.probability) == ("final_none", NONE_LABEL, 0.8)

    @pytest.mark.asyncio
    async def test_more_winners_than_fit_make_a_nested_round(self):
        # 60 names, 3 per chunk: 20 chunks, 9 of them with a winner (c0..c8),
        # so one nested round of 3 chunks, then the final: 20 + 3 + 1 requests.
        names = [f"N{i:03d}" for i in range(60)]
        script = {f"c{i}": [{names[i * 3]: 0.6 if i == 0 else 0.9}] for i in range(9)}
        for i in range(9, 20):
            script[f"c{i}"] = [{NONE_LABEL: 0.9}]
        for i in range(3):  # nested chunk i holds the winners names[9i], names[9i+3], names[9i+6]
            script[f"c{i}"].append({names[i * 9]: 0.9})
        script["final"] = {names[0]: 0.95}
        s = _service(script, max_options=4)
        d = await _decide(s, names)
        assert (d.index, d.probability, d.requests) == (0, 0.6, 24)

    @pytest.mark.asyncio
    async def test_a_nested_round_that_picks_none_is_a_review(self):
        names = [f"N{i:03d}" for i in range(60)]
        script = {f"c{i}": [{names[i * 3]: 0.9}] for i in range(9)}
        for i in range(9, 20):
            script[f"c{i}"] = [{NONE_LABEL: 0.9}]
        for i in range(3):
            script[f"c{i}"].append({names[i * 9]: 0.9})
        script["c1"][1] = {NONE_LABEL: 0.9}
        script["final"] = {names[0]: 0.95}
        s = _service(script, max_options=4)
        d = await _decide(s, names)
        assert (d.index, d.choice, d.review_reason, d.requests) == (None, NONE_LABEL, "final_none", 23)

    @pytest.mark.asyncio
    async def test_low_mass_in_a_sub_final_is_a_review(self):
        names = [f"N{i:03d}" for i in range(60)]
        script = {f"c{i}": [{names[i * 3]: 0.9}] for i in range(9)}
        for i in range(9, 20):
            script[f"c{i}"] = [{NONE_LABEL: 0.9}]
        for i in range(3):
            script[f"c{i}"].append({names[i * 9]: 0.9})
        script["final"] = {names[0]: 0.95}
        s = _service(script, masses={"c0": [1.0, 0.3]}, max_options=4)
        d = await _decide(s, names)
        assert (d.index, d.review_reason) == (0, "low_mass")

    @pytest.mark.asyncio
    async def test_low_mass_in_the_deciding_round_is_a_review(self):
        s = _service({"c0": {"Firma 003": 0.95}, "c1": {NONE_LABEL: 0.9}, "c2": {NONE_LABEL: 0.9}}, masses={"c0": 0.3})
        d = await _decide(s, NAMES[:40])
        assert (d.review_reason, d.index) == ("low_mass", 3)

    @pytest.mark.asyncio
    async def test_low_mass_in_a_losing_chunk_does_not_matter(self):
        s = _service({"c0": {"Firma 003": 0.95}, "c1": {NONE_LABEL: 0.9}, "c2": {NONE_LABEL: 0.9}}, masses={"c1": 0.1})
        d = await _decide(s, NAMES[:40])
        assert d.review_reason is None

    @pytest.mark.asyncio
    async def test_a_round_without_letters_falls_back(self):
        s = _service({"c0": "no_letters", "c1": {NONE_LABEL: 0.9}, "c2": {NONE_LABEL: 0.9}})
        d = await _decide(s, NAMES[:40])
        assert (d.fallback_reason, d.requests) == ("no_letters", 1)
        assert d.method == "fake"
        assert s._unsupported_until is None

    @pytest.mark.asyncio
    async def test_a_provider_without_logprobs_is_remembered(self):
        s = _service({"c0": "unsupported"})
        d = await _decide(s, NAMES[:5])
        assert (d.fallback_reason, d.fallback_detail) == ("no_logprobs", "200 without logprobs")
        assert d.method == "fake"
        again = await _decide(s, NAMES[:5])
        assert again.fallback_reason == "no_logprobs" and again.requests == 0
        assert again.method == "text"

    @pytest.mark.asyncio
    async def test_an_empty_list_sends_nothing(self):
        s = _service({})
        d = await _decide(s, [])
        assert (d.fallback_reason, d.requests) == ("empty_list", 0)
        assert d.method == "text"

    @pytest.mark.asyncio
    async def test_the_model_is_noted_once_and_only_when_asked(self):
        class Ctx:
            preview = False

            def __init__(self):
                self.noted = []

            def note_model(self, h):
                self.noted.append((h.provider, h.model))

        ctx = Ctx()
        s = _service({"c0": {"Firma 003": 0.95}, "c1": {NONE_LABEL: 0.9}, "c2": {NONE_LABEL: 0.9}})
        await _decide(s, NAMES[:40], ctx=ctx)
        assert ctx.noted == [("ollama", "fake")]
        ctx2 = Ctx()
        await _decide(_service({}), [], ctx=ctx2)
        assert ctx2.noted == []

    @pytest.mark.asyncio
    async def test_the_full_request_is_kept_in_preview_only(self):
        class Ctx:
            preview = True

            def note_model(self, h): ...

        s = _service({"c0": {"Firma 003": 0.95}})
        d = await _decide(s, NAMES[:5], ctx=Ctx())
        assert d.full == "<c0:text>" and d.rendered == "<c0>"
        d2 = await _decide(_service({"c0": {"Firma 003": 0.95}}), NAMES[:5])
        assert d2.full is None and d2.text_chars == 4

    @pytest.mark.asyncio
    async def test_the_top_three_name_the_options(self):
        s = _service({"c0": {"Firma 003": 0.5, "Firma 001": 0.3, NONE_LABEL: 0.15, "Firma 002": 0.05}})
        d = await _decide(s, NAMES[:5])
        assert d.top == [{"name": "Firma 003", "p": 0.5}, {"name": "Firma 001", "p": 0.3}, {"name": NONE_LABEL, "p": 0.15}]
