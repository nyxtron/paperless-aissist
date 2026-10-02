"""How the options reach the model.

Three renderings, all pinned to the ones the 60-document measurement used:
the letter block for any instruct model, Nimble's JSON for /api/chat, and the
questions map for Ollama's /v1/systemone. No prompt wording lives here; the
letter prompt comes from the prompt table and Nimble's from the model.
"""

import hashlib
import json
from typing import Any, Iterable, Mapping

NONE_LABEL = "None of these"
NONE_DESCRIPTION = "The right answer is not in this list."
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TEXT_PLACEHOLDER = "<document text, {chars} chars>"
NIMBLE_FIELD = "field"


def text_digest(text: str) -> dict[str, Any]:
    """Length and a short hash, so a stored request can be matched to its
    preview without storing the document."""
    return {
        "text_chars": len(text),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
    }


def letter_block(labels: Iterable[str]) -> str:
    return "\n".join(f"{LETTERS[i]}: {label}" for i, label in enumerate(labels))


def render_letter_prompt(template: str, text: str, question: str, labels: list[str]) -> str:
    """Fill the decision prompt. A template that lost {options} still gets the
    block, appended, or the model would have nothing to pick from."""
    block = letter_block(labels)
    out = template.replace("{content}", text).replace("{question}", question)
    if "{options}" in out:
        return out.replace("{options}", block)
    return f"{out}\n\nOptions:\n{block}"


def go_json(value: Any) -> str:
    """json.dumps the way Go does it: compact, and <, >, & escaped."""
    s = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return (
        s.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def nimble_user_message(
    text: str, question: str, labels: list[str], descriptions: Mapping[str, str]
) -> str:
    """The user message Nimble was trained on; Ollama adds the system prompt."""
    choices = [
        {"code": LETTERS[i], "value": label, "description": descriptions.get(label, label)}
        for i, label in enumerate(labels)
    ]
    payload = {
        "context": text,
        "schema": [{"name": NIMBLE_FIELD, "description": question, "choices": choices}],
    }
    return f"{go_json(payload)}\n\nRequested field: {go_json(NIMBLE_FIELD)}"


def unique_keys(labels: Iterable[str]) -> list[str]:
    """Option texts as map keys: a second "Telekom" becomes "Telekom (2)".

    The sentinel is appended last by the adapter and keeps its plain key; a
    real option spelled like it moves out of its way.
    """
    labels = list(labels)
    last_none = max((i for i, label in enumerate(labels) if label == NONE_LABEL), default=-1)
    seen: dict[str, int] = {}
    keys = []
    for i, label in enumerate(labels):
        if label == NONE_LABEL and i == last_none:
            keys.append(NONE_LABEL)
            continue
        seen[label] = seen.get(label, 0) + 1
        count = seen[label] + (1 if label == NONE_LABEL else 0)
        keys.append(label if count == 1 else f"{label} ({count})")
    return keys


def systemone_questions(
    question: str, asks: list[tuple[str, list[str]]], descriptions: Mapping[str, str]
) -> dict[str, Any]:
    """One choice question per round, keyed by the round name."""
    out = {}
    for name, labels in asks:
        criteria = {}
        for key, label in zip(unique_keys(labels), labels):
            criteria[key] = descriptions.get(label)
        out[name] = {"type": "choice", "instructions": question, "criteria": criteria}
    return out
