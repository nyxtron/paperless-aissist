"""The reworded OCR prompt has to reach installations that already exist (#45).

Prompts are only seeded when missing, never rewritten on startup. What carries
a change to existing users is sample_status: a prompt the user never touched
still matches the hash it was seeded with, so once the shipped sample moves on
it reports sample_update_available and the Prompts page offers the new text.
If that signal did not fire, the marker would only ever reach fresh installs.
"""

from datetime import datetime, timezone

from app.models import Prompt
from app.services.prompt_samples import load_samples, sample_hash, sample_status

OLD_TEXT = (
    "Extract all text from this document image exactly as it appears. "
    "Return only the raw text content — no JSON, no markdown, no explanations."
)


def _vision_sample() -> dict:
    return next(s for s in load_samples().values() if s["prompt_type"] == "vision_ocr")


def test_the_shipped_prompt_now_carries_the_marker():
    assert "reply with exactly NO_TEXT" in _vision_sample()["system_prompt"]


def test_an_untouched_old_prompt_is_offered_the_update():
    sample = _vision_sample()
    old_sample = {**sample, "system_prompt": OLD_TEXT}
    now = datetime.now(timezone.utc)
    seeded_before = Prompt(
        name=sample["name"],
        prompt_type=sample["prompt_type"],
        document_type_filter=sample.get("document_type_filter"),
        system_prompt=OLD_TEXT,
        user_template=sample.get("user_template", ""),
        is_active=True,
        sample_key=sample["sample_key"],
        sample_hash=sample_hash(old_sample),
        created_at=now,
        updated_at=now,
    )

    assert sample_status(seeded_before, sample) == "sample_update_available"


def test_a_prompt_the_user_edited_is_left_alone():
    """Someone who wrote their own wording must not be nudged to overwrite it."""
    sample = _vision_sample()
    now = datetime.now(timezone.utc)
    edited = Prompt(
        name=sample["name"],
        prompt_type=sample["prompt_type"],
        document_type_filter=sample.get("document_type_filter"),
        system_prompt="Transcribe this page in German, keep the layout.",
        user_template=sample.get("user_template", ""),
        is_active=True,
        sample_key=sample["sample_key"],
        sample_hash=sample_hash({**sample, "system_prompt": OLD_TEXT}),
        created_at=now,
        updated_at=now,
    )

    assert sample_status(edited, sample) == "modified"
