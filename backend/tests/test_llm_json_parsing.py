"""Lenient JSON parsing of LLM responses (regression for issue #35).

Ollama (and other providers) sometimes wrap their JSON in a ```json ... ```
markdown fence — or prepend a stray word — even when JSON mode is requested.
The parser must recover the object/array instead of failing.
"""

import json
import pathlib

from app.services.llm_handler import _loads_llm_json


def test_fenced_object_from_issue_35():
    # Exact shape from the issue log: a leading "json" line plus a ```json fence.
    raw = (
        'json\n```json\n'
        '{"created_date":"2019-04-25","confidence":"high",'
        '"evidence":"Statement Date 04/25/2019"}\n```'
    )
    assert _loads_llm_json(raw) == {
        "created_date": "2019-04-25",
        "confidence": "high",
        "evidence": "Statement Date 04/25/2019",
    }


def test_plain_json_object_unchanged():
    assert _loads_llm_json('{"a": 1}') == {"a": 1}


def test_fenced_array_recovered():
    assert _loads_llm_json('```json\n[{"x": 1}, {"y": 2}]\n```') == [{"x": 1}, {"y": 2}]


def test_prose_wrapped_object():
    raw = 'Here is the result:\n{"confidence": "low"}\nHope that helps.'
    assert _loads_llm_json(raw) == {"confidence": "low"}


def test_braces_inside_strings_are_respected():
    assert _loads_llm_json('{"evidence": "amount {net}"}') == {"evidence": "amount {net}"}


def test_duplicated_objects_collapse_to_one():
    # Follow-up in issue #35: the model sometimes emits the object twice.
    raw = '{"created_date":"2019-04-25","confidence":"high"}\n{"created_date":"2019-04-25","confidence":"high"}'
    assert _loads_llm_json(raw) == {"created_date": "2019-04-25", "confidence": "high"}


def test_fenced_duplicated_objects_collapse_to_one():
    raw = '```json\n{"confidence":"high"}\n{"confidence":"high"}\n```'
    assert _loads_llm_json(raw) == {"confidence": "high"}


def test_unparseable_falls_back_to_raw():
    assert _loads_llm_json("not json at all") == {"raw": "not json at all"}


def test_prompt_example_is_not_mistaken_for_the_answer():
    """The extract prompt ships an example, and models like to restate it.

    Taking the earlier match wrote the example's amount to Paperless as though
    it had been read off the document.
    """
    raw = (
        'Following the format Example: [{"field": "rechnungsbetrag", "value": "USD123.45"}]\n'
        'here is the result:\n'
        '[{"field": "rechnungsbetrag", "value": "EUR219.40"}]'
    )
    assert _loads_llm_json(raw) == [{"field": "rechnungsbetrag", "value": "EUR219.40"}]


def test_fenced_answer_wins_over_a_fenced_example():
    raw = (
        'Example:\n```json\n{"created_date":null,"confidence":"low"}\n```\n'
        'Result:\n```json\n{"created_date":"2026-03-17","confidence":"high"}\n```'
    )
    assert _loads_llm_json(raw) == {
        "created_date": "2026-03-17",
        "confidence": "high",
    }


def test_citation_before_the_json_is_ignored():
    """A leading "[1]" is balanced and parses, but it is not the answer."""
    raw = 'See [1] for details.\n```json\n{"created_date":"2026-03-17"}\n```'
    assert _loads_llm_json(raw) == {"created_date": "2026-03-17"}


def test_truncated_object_is_not_silently_half_parsed():
    raw = '{"created_date":"2026-03-17","evidence":"Rechnungsdatum 17.03.'
    assert _loads_llm_json(raw) == {"raw": raw}


def test_trailing_citation_does_not_outrank_the_answer():
    """"[1]" parses cleanly but is prose, not a reply the steps can use."""
    raw = (
        '{"created_date": "2026-03-17", "confidence": "high", "evidence": "Rechnungsdatum"}\n'
        'Source: invoice header [1]'
    )
    assert _loads_llm_json(raw) == {
        "created_date": "2026-03-17",
        "confidence": "high",
        "evidence": "Rechnungsdatum",
    }


def test_trailing_empty_list_does_not_discard_extracted_fields():
    raw = '[{"field": "rechnungsbetrag", "value": "EUR219.40"}]\nNothing else matched, so: []'
    assert _loads_llm_json(raw) == [{"field": "rechnungsbetrag", "value": "EUR219.40"}]


def test_trailing_entry_number_does_not_replace_the_correspondent():
    raw = '{"name": "Stadtwerke Muenchen", "is_existing": true}\nMatched entry [3] of the list.'
    assert _loads_llm_json(raw) == {"name": "Stadtwerke Muenchen", "is_existing": True}


def test_empty_list_still_survives_on_its_own():
    """The extract prompt returns [] when there is nothing to extract."""
    assert _loads_llm_json("Nothing to extract here: []") == []


class TestEchoedPromptExample:
    """The example belongs to us, so a reply quoting it back is not an answer.

    Which of the two comes first varies by model, so position alone cannot tell
    them apart — the prompt has to be handed in.
    """

    @staticmethod
    def extract_prompt() -> str:
        path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "examples/prompts/custom-fields-extraction.json"
        )
        prompt = json.loads(path.read_text())
        return f"{prompt['system_prompt']}\n{prompt['user_template']}"

    def test_bundled_prompt_still_carries_the_example(self):
        # If this ever fails the prompt was reworded and the tests below went blind.
        assert '"value": "USD123.45"' in self.extract_prompt()

    def test_example_quoted_before_the_answer_is_dropped(self):
        raw = (
            'Example: [{"field": "rechnungsbetrag", "value": "USD123.45"}]\n'
            'Result:\n[{"field": "rechnungsbetrag", "value": "EUR219.40"}]'
        )
        assert _loads_llm_json(raw, self.extract_prompt()) == [
            {"field": "rechnungsbetrag", "value": "EUR219.40"}
        ]

    def test_example_appended_after_the_answer_is_dropped(self):
        raw = (
            '```json\n[{"field": "rechnungsbetrag", "value": "EUR84.20"}]\n```\n'
            'The format follows the example:\n'
            '```json\n[{"field": "rechnungsbetrag", "value": "USD123.45"}]\n```'
        )
        assert _loads_llm_json(raw, self.extract_prompt()) == [
            {"field": "rechnungsbetrag", "value": "EUR84.20"}
        ]

    def test_empty_answer_beats_the_echoed_example(self):
        """A contract has nothing to extract, and [] must not lose to the example."""
        raw = (
            "This document is a school enrolment contract, not an invoice.\n"
            'Example: [{"field": "rechnungsbetrag", "value": "USD123.45"}]\n'
            "Since there is no payable total, my answer is: []"
        )
        assert _loads_llm_json(raw, self.extract_prompt()) == []

    def test_a_lone_answer_survives_even_when_it_matches_the_example(self):
        """Quoting only ever hands the decision to a competing value.

        A document whose amount happens to equal the example's would otherwise
        be left with nothing at all, and for the date prompt that meant failing
        the document over the very answer it asks for.
        """
        raw = 'The invoice total is USD123.45.\n[{"field": "rechnungsbetrag", "value": "USD123.45"}]'
        assert _loads_llm_json(raw, self.extract_prompt()) == [
            {"field": "rechnungsbetrag", "value": "USD123.45"}
        ]

    def test_the_date_prompts_own_no_date_answer_survives(self):
        """The date prompt prints this object as a valid example, verbatim.

        A document without a reliable date gets exactly it back. Dropping it as
        a quote failed the step, and since the trigger tag only comes off after
        a clean run, the scheduler picked the document up again every pass.
        """
        path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "examples/prompts/date-detection.json"
        )
        prompt = json.loads(path.read_text())
        full = f"{prompt['system_prompt']}\n{prompt['user_template']}"
        assert '"created_date":null,"confidence":"low"' in full.replace(" ", "")

        raw = '```json\n{\n  "created_date": null,\n  "confidence": "low",\n  "evidence": ""\n}\n```'
        assert _loads_llm_json(raw, full) == {
            "created_date": None,
            "confidence": "low",
            "evidence": "",
        }
