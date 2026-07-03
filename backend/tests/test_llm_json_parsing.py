"""Lenient JSON parsing of LLM responses (regression for issue #35).

Ollama (and other providers) sometimes wrap their JSON in a ```json ... ```
markdown fence — or prepend a stray word — even when JSON mode is requested.
The parser must recover the object/array instead of failing.
"""

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


def test_unparseable_falls_back_to_raw():
    assert _loads_llm_json("not json at all") == {"raw": "not json at all"}
