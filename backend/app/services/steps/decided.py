"""What the decision steps share: the settings they read per document, the
details they log, and the review result."""

from typing import Any, Mapping

from ..decision import DEFAULT_QUESTIONS, Decision
from .base import StepContext, StepResult

DECISION_FIELDS = ("correspondent", "document_type")
DEFAULT_THRESHOLD = 0.9
THRESHOLD_MIN, THRESHOLD_MAX = 0.5, 1.0


def decision_enabled(config: Mapping[str, Any], field: str) -> bool:
    return str(config.get(f"decision_{field}") or "").strip().lower() == "true"


def decision_threshold(config: Mapping[str, Any], field: str) -> float:
    """The saved threshold, or the default when the stored text is not one."""
    raw = config.get(f"decision_threshold_{field}")
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD
    if not THRESHOLD_MIN <= value <= THRESHOLD_MAX:
        return DEFAULT_THRESHOLD
    return value


def decision_question(config: Mapping[str, Any], field: str) -> str:
    raw = config.get(f"decision_question_{field}")
    return str(raw).strip() if raw and str(raw).strip() else DEFAULT_QUESTIONS[field]


def decision_details(
    decision: Decision, threshold: float, outcome: str, reason: str | None = None
) -> dict[str, Any]:
    """The step detail every view reads (processing panel, preview, dashboard, MCP)."""
    request: dict[str, Any] = {
        "text_chars": decision.text_chars,
        "text_sha256": decision.text_sha256,
        "rendered": decision.rendered,
    }
    if decision.full is not None:
        request["full"] = decision.full
    return {
        "method": decision.method,
        "provider": decision.provider,
        "model": decision.model,
        "outcome": outcome,
        "reason": reason,
        "choice": decision.choice,
        "probability": decision.probability,
        "threshold": threshold,
        "top": decision.top,
        "requests": decision.requests,
        "mass": decision.mass,
        "fallback_reason": decision.fallback_reason,
        "fallback_detail": decision.fallback_detail,
        "request": request,
    }


def review(
    ctx: StepContext, field: str, decision: Decision, threshold: float, reason: str
) -> StepResult:
    """Leave the field alone and ask for a look: the processor adds the tag."""
    if field not in ctx.review_fields:
        ctx.review_fields.append(field)
    return StepResult(
        data={}, skipped=True, details={"decision": decision_details(decision, threshold, "review", reason)}
    )
