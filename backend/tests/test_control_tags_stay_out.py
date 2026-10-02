"""The model is never offered, and never given, the tags that steer processing.

The tags step used to list every Paperless tag, the pipeline's own ones
included. A picked ai-ocr sent the document through vision OCR again on the
next pass and overwrote its content; a picked force_ocr was never taken off.
The blacklist was dropped from the answer but still listed as a choice.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.control_tags import (
    assignable_tags,
    blacklisted_tag_names,
    control_tag_names,
)
from app.services.steps.base import StepContext
from app.services.steps.tags_step import TagsStep

PAPERLESS_TAGS = [
    {"id": 1, "name": "ai-process"},
    {"id": 2, "name": "ai-processed"},
    {"id": 3, "name": "ai-ocr"},
    {"id": 4, "name": "ai-ocr-fix"},
    {"id": 5, "name": "ai-title"},
    {"id": 6, "name": "ai-date"},
    {"id": 7, "name": "force_ocr"},
    {"id": 8, "name": "force-ocr-fix"},
    {"id": 9, "name": "Steuer"},
    {"id": 10, "name": "Versicherung"},
    {"id": 11, "name": "reviewed"},
]
CONFIG = {
    "process_tag": "ai-process",
    "processed_tag": "ai-processed",
    "tag_blacklist": "reviewed",
}


class TestWhichTagsAreControlTags:
    def test_the_defaults_count_even_when_nothing_is_configured(self):
        names = control_tag_names({})

        assert {"ai-process", "ai-ocr", "ai-ocr-fix", "ai-title", "ai-date",
                "ai-tags", "ai-fields", "ai-correspondent", "ai-document-type",
                "force_ocr", "force-ocr-fix"} <= names

    def test_renamed_tags_are_followed(self):
        names = control_tag_names({"modular_tag_ocr": "Scan-Neu", "force_ocr_tag": "OCR!"})

        assert "scan-neu" in names and "ocr!" in names
        assert "ai-ocr" not in names

    def test_the_process_and_processed_tags_count(self):
        names = control_tag_names({"process_tag": "Inbox-KI", "processed_tag": "KI-fertig"})

        assert {"inbox-ki", "ki-fertig"} <= names

    def test_the_blacklist_is_read_like_the_setting_is_written(self):
        assert blacklisted_tag_names({"tag_blacklist": " Reviewed , inbox,, "}) == {"reviewed", "inbox"}
        assert blacklisted_tag_names({}) == set()

    def test_only_descriptive_tags_are_assignable(self):
        names = [t["name"] for t in assignable_tags(PAPERLESS_TAGS, CONFIG)]

        assert names == ["Steuer", "Versicherung"]

    def test_case_and_spacing_do_not_let_a_control_tag_through(self):
        tags = [{"id": 1, "name": " AI-OCR "}, {"id": 2, "name": "Steuer"}]

        assert [t["name"] for t in assignable_tags(tags, {})] == ["Steuer"]

    def test_the_review_tag_counts(self):
        assert "ai-review" in control_tag_names({})
        assert "needs-check" in control_tag_names({"review_tag": "needs-check"})
        assert "ai-review" not in control_tag_names({"review_tag": "needs-check"})

    def test_the_review_tag_is_not_a_trigger_tag(self):
        from app.services.control_tags import FORCE_TAG_DEFAULTS, MODULAR_TAG_DEFAULTS

        assert "review_tag" not in MODULAR_TAG_DEFAULTS and "review_tag" not in FORCE_TAG_DEFAULTS


def _ctx(reply: str) -> StepContext:
    llm = MagicMock()
    llm.provider = "ollama"
    llm.model = "qwen2.5:7b"
    llm.complete = AsyncMock(return_value={"text": reply})
    paperless = MagicMock()
    paperless.get_tags = AsyncMock(return_value=PAPERLESS_TAGS)
    return StepContext(
        doc_id=1,
        paperless=paperless,
        llm=llm,
        config={**CONFIG, "modular_tag_process": "ai-process"},
        trigger_tags={"ai-process"},
        ocr_text="Beitragsbescheid der Krankenkasse",
    )


async def _run(ctx: StepContext, step_config: dict | None = None):
    prompt = MagicMock()
    prompt.system_prompt = "Assign tags."
    prompt.user_template = "Tags: {tags_list}\n\n{content}"
    session = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=prompt)))
    with patch("app.database.get_async_session") as db:
        db.return_value.__aenter__.return_value = session
        step = await TagsStep.from_config(step_config if step_config is not None else ctx.config)
        return await step.execute(ctx)


class TestTheTagsStep:
    @pytest.mark.asyncio
    async def test_the_model_is_not_offered_control_or_blacklisted_tags(self):
        ctx = _ctx("Steuer")

        await _run(ctx)

        sent = ctx.llm.complete.await_args.kwargs["user_prompt"]
        assert '"Steuer"' in sent and '"Versicherung"' in sent
        for name in ("ai-process", "ai-processed", "ai-ocr", "force_ocr", "force-ocr-fix", "reviewed"):
            assert f'"{name}"' not in sent, name

    @pytest.mark.asyncio
    async def test_a_control_tag_in_the_reply_is_not_assigned(self):
        """The reported case: this reply used to end with ai-ocr and force_ocr
        on the document, and the next pass ran vision OCR again."""
        result = await _run(_ctx("Steuer, ai-ocr, force_ocr, ai-process"))

        assert result.data == {"tags": [9]}

    @pytest.mark.asyncio
    async def test_a_blacklisted_tag_in_the_reply_is_still_not_assigned(self):
        result = await _run(_ctx("reviewed, Versicherung"))

        assert result.data == {"tags": [10]}

    @pytest.mark.asyncio
    async def test_a_reply_of_only_control_tags_assigns_nothing(self):
        result = await _run(_ctx("ai-ocr, force_ocr"))

        assert not result.data.get("tags")

    @pytest.mark.asyncio
    async def test_a_renamed_review_tag_is_read_per_document(self):
        """The step was built with one config; the document carries the live one."""
        ctx = _ctx("Steuer")
        ctx.paperless.get_tags = AsyncMock(return_value=[
            {"id": 1, "name": "needs-check"}, {"id": 2, "name": "ai-review"}, {"id": 3, "name": "Steuer"}])
        ctx.config = {**ctx.config, "review_tag": "needs-check"}

        await _run(ctx, step_config={"modular_tag_process": "ai-process"})

        sent = ctx.llm.complete.await_args.kwargs["user_prompt"]
        assert '"needs-check"' not in sent and '"ai-review"' in sent and '"Steuer"' in sent
