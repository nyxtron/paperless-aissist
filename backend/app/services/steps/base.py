"""Base classes and data structures for the step-based processing pipeline.

Provides StepResult (output data + error), StepContext (shared execution context),
and AbstractStep (abstract base that each processing step must implement).
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.paperless import PaperlessClient
    from app.services.llm_handler import LLMHandler


@dataclass
class StepResult:
    """Result of a step execution.

    Attributes:
        data: Dict of proposed changes (title, tags, custom_fields, etc.).
        error: Error message string if the step failed, None on success.
    """

    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class StepContext:
    """Shared execution context passed to every step.

    Attributes:
        doc_id: Paperless document ID.
        paperless: Shared PaperlessClient instance.
        llm: Shared LLMHandler instance.
        config: Full application config dict.
        trigger_tags: Tags currently on the document.
        ocr_text: Extracted or provided text content.
        detected_type: Set by DocumentTypeStep; read by FieldsStep for type-specific prompts.
    """

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
    """Abstract base for a processing step.

    Each concrete step must implement can_handle (tag-based routing), execute
    (LLM call + result construction), and from_config (config-driven factory).
    """

    name: str

    @abstractmethod
    def can_handle(self, tags: set[str]) -> bool:
        """Return True if this step should run given the document's current tags."""

    @abstractmethod
    async def execute(self, ctx: StepContext) -> StepResult:
        """Execute the step logic and return a StepResult."""

    @classmethod
    @abstractmethod
    async def from_config(cls, config: dict[str, str]) -> "AbstractStep":
        """Construct step instance from the full config dict."""

    async def update_metadata(self, ctx: StepContext, result: StepResult) -> None:
        """Optional hook to apply step results back to Paperless metadata."""

    def _match_tag(self, doc_tags: set[str], target: str) -> bool:
        """Return True if target tag is present in doc_tags."""
        return target in doc_tags
