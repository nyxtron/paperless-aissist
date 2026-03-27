import logging

from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)

_MODULAR_TAG_CONFIG_KEYS = [
    ("modular_tag_process", "ai-process"),
    ("modular_tag_ocr", "ai-ocr"),
    ("modular_tag_ocr_fix", "ai-ocr-fix"),
    ("modular_tag_title", "ai-title"),
    ("modular_tag_correspondent", "ai-correspondent"),
    ("modular_tag_document_type", "ai-document-type"),
    ("modular_tag_tags", "ai-tags"),
    ("modular_tag_fields", "ai-fields"),
]


class ModularTagsStep(AbstractStep):
    name = "modular_tags"

    def __init__(self, config):
        self.config = config

    @classmethod
    async def from_config(cls, config):
        return cls(config)

    def _all_modular_tag_names(self) -> set[str]:
        return {self.config.get(key) or default for key, default in _MODULAR_TAG_CONFIG_KEYS}

    def can_handle(self, tags: set[str]) -> bool:
        return bool(tags & self._all_modular_tag_names())

    async def execute(self, ctx: StepContext) -> StepResult:
        modular_tag_names = self._all_modular_tag_names()

        all_tags = await ctx.paperless.get_tags()
        tags_by_name = {t["name"]: t["id"] for t in all_tags}

        doc = await ctx.paperless.get_document(ctx.doc_id)
        existing_tag_ids = set(doc.get("tags", []))

        # Remove every modular trigger tag that is currently on the document
        remove_tags = [
            tags_by_name[name]
            for name in modular_tag_names
            if name in tags_by_name and tags_by_name[name] in existing_tag_ids
        ]

        logger.debug(
            f"ModularTagsStep: remove {remove_tags} for doc {ctx.doc_id}"
        )

        return StepResult(
            data={"remove_tags": remove_tags, "add_tags": []}, error=None
        )

    async def update_metadata(self, ctx: StepContext, result: StepResult) -> None:
        pass
