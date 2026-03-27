from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.paperless import PaperlessClient
    from app.services.llm_handler import LLMHandler


@dataclass
class StepResult:
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class StepContext:
    doc_id: int
    paperless: PaperlessClient
    llm: LLMHandler
    config: dict[str, str]
    trigger_tags: set[str]
    ocr_text: str | None = None
    # NOTE: Set by DocumentTypeStep.execute(). FieldsStep reads this to find
    # type_specific prompts. DocumentTypeStep MUST run before FieldsStep in
    # the step list — this ordering is enforced by _build_steps() in processor.py.
    detected_type: str | None = None

    async def get_document(self):
        return await self.paperless.get_document(self.doc_id)


class AbstractStep(ABC):
    name: str

    @abstractmethod
    def can_handle(self, tags: set[str]) -> bool:
        pass

    @abstractmethod
    async def execute(self, ctx: StepContext) -> StepResult:
        pass

    @classmethod
    @abstractmethod
    async def from_config(cls, config: dict[str, str]) -> "AbstractStep":
        """Construct step instance from the full config dict."""
        pass

    async def update_metadata(self, ctx: StepContext, result: StepResult) -> None:
        pass

    def _match_tag(self, doc_tags: set[str], target: str) -> bool:
        return target in doc_tags
