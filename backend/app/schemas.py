"""Pydantic response models for API endpoints."""

from pydantic import BaseModel
from typing import Optional


class StatusResponse(BaseModel):
    """Health-check response."""

    status: str
    service: str


class ConfigResponse(BaseModel):
    """Key-value config response with sensitive keys excluded.

    Sensitive keys (tokens, API keys) are not returned at all.
    The ``secrets_set`` field lists which sensitive keys have a non-empty
    value stored in the database, so the UI knows whether a secret is
    already configured without knowing the actual value.
    """

    data: dict[str, str]
    secrets_set: list[str] = []


class ConfigDetailResponse(BaseModel):
    """Single config entry with optional description."""

    key: str
    value: str
    description: Optional[str] = None


class ConfigDeleteResponse(BaseModel):
    """Response after deleting a config key."""

    success: bool
    message: str


class DailyStatsItem(BaseModel):
    """Daily processing statistics."""

    date: str
    total: int
    success: int
    failed: int


class RecentLogItem(BaseModel):
    """A single recent processing log entry."""

    id: int
    document_id: Optional[int] = None
    document_title: Optional[str] = None
    status: str
    provider: Optional[str] = None
    model: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: Optional[str] = None


class StatsResponse(BaseModel):
    """Aggregate processing statistics."""

    total_processed: int
    success_rate: float


class PromptResponse(BaseModel):
    """Full prompt template response."""

    id: int
    name: str
    prompt_type: str
    document_type_filter: Optional[str] = None
    system_prompt: str
    user_template: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
