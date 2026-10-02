"""The three option renderings, pinned to what was measured on the archive."""

import json

from app.services.decision.formats import (
    NONE_DESCRIPTION,
    NONE_LABEL,
    TEXT_PLACEHOLDER,
    go_json,
    letter_block,
    nimble_user_message,
    render_letter_prompt,
    systemone_questions,
    text_digest,
    unique_keys,
)


def test_the_letter_block_numbers_options_and_ends_with_none():
    assert letter_block(["Amazon", "Telekom", NONE_LABEL]) == "A: Amazon\nB: Telekom\nC: None of these"


def test_the_template_placeholders_are_filled():
    out = render_letter_prompt("Doc:\n{content}\n{question}\n{options}\nLetter only.", "text here",
                               "Who sent it?", ["Amazon", NONE_LABEL])
    assert out == "Doc:\ntext here\nWho sent it?\nA: Amazon\nB: None of these\nLetter only."


def test_a_template_without_options_still_gets_the_block():
    out = render_letter_prompt("Doc: {content}\n{question}", "t", "Q?", ["X", NONE_LABEL])
    assert out.endswith("Q?\n\nOptions:\nA: X\nB: None of these")


def test_go_json_is_compact_and_escapes_like_ollama():
    # Written as escapes on purpose: the raw U+2028/U+2029 characters are invisible.
    assert go_json({"a": "<b> & c"}) == '{"a":"\\u003cb\\u003e \\u0026 c"}'
    assert go_json("ä\u2028") == '"ä\\u2028"'


def test_the_nimble_message_matches_the_measured_rendering():
    msg = nimble_user_message("Rechnung der Stadtwerke", "Who sent this document (the correspondent)?",
                              ["Stadtwerke Saarbrücken", "Telekom", NONE_LABEL], {NONE_LABEL: NONE_DESCRIPTION})
    payload, _, tail = msg.partition("\n\nRequested field: ")
    assert tail == '"field"'
    data = json.loads(payload)
    assert data["context"] == "Rechnung der Stadtwerke"
    assert data["schema"][0]["name"] == "field"
    assert data["schema"][0]["description"] == "Who sent this document (the correspondent)?"
    assert data["schema"][0]["choices"] == [
        {"code": "A", "value": "Stadtwerke Saarbrücken", "description": "Stadtwerke Saarbrücken"},
        {"code": "B", "value": "Telekom", "description": "Telekom"},
        {"code": "C", "value": NONE_LABEL, "description": NONE_DESCRIPTION},
    ]
    assert payload.index('"context"') < payload.index('"schema"')
    assert ", " not in payload.replace("Stadtwerke Saarbrücken", "")


def test_duplicate_keys_get_suffixes_and_the_sentinel_stays_unique():
    # The adapter appends the sentinel last; only that last one keeps the plain key.
    assert unique_keys(["Telekom", "Telekom", "None of these", "Telekom", NONE_LABEL]) == [
        "Telekom", "Telekom (2)", "None of these (2)", "Telekom (3)", "None of these"]


def test_the_systemone_questions_match_the_measured_request():
    q = systemone_questions("Who sent it?", [("c0", ["A GmbH", "B AG", NONE_LABEL]), ("c1", ["C KG", NONE_LABEL])],
                            {NONE_LABEL: NONE_DESCRIPTION})
    assert q == {
        "c0": {"type": "choice", "instructions": "Who sent it?",
               "criteria": {"A GmbH": None, "B AG": None, NONE_LABEL: NONE_DESCRIPTION}},
        "c1": {"type": "choice", "instructions": "Who sent it?",
               "criteria": {"C KG": None, NONE_LABEL: NONE_DESCRIPTION}},
    }


def test_the_digest_is_short_and_stable():
    d = text_digest("abc")
    assert d == {"text_chars": 3, "text_sha256": "ba7816bf8f01cfea"}
    assert TEXT_PLACEHOLDER.format(chars=3) == "<document text, 3 chars>"
