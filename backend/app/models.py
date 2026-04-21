"""SQLModel table definitions for Paperless-AIssist.

Defines the core database models: Config (key-value store), Prompt (LLM prompt
templates), and ProcessingLog (audit trail).
"""

from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, Index, SQLModel


class Config(SQLModel, table=True):
    """Key-value configuration store.

    Attributes:
        id: Primary key.
        key: Unique configuration key.
        value: Configuration value.
        description: Optional human-readable description.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "config"

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value: str
    description: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Prompt(SQLModel, table=True):
    """LLM prompt template.

    Attributes:
        id: Primary key.
        name: Unique prompt name.
        prompt_type: Type of prompt (e.g., classify, title, extract).
        document_type_filter: Optional filter for specific document types.
        system_prompt: System-level instructions for the LLM.
        user_template: User prompt template with variable placeholders.
        is_active: Whether this prompt is enabled.
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "prompts"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    prompt_type: str = Field(default="classify")
    document_type_filter: Optional[str] = None
    system_prompt: str
    user_template: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProcessingLog(SQLModel, table=True):
    """Audit log for document processing operations.

    Attributes:
        id: Primary key.
        document_id: Paperless document ID.
        document_title: Cached title at time of processing.
        status: Outcome status (success, failed, skipped).
        llm_provider: LLM provider used.
        llm_model: LLM model used.
        llm_response: Raw LLM response (JSON string).
        error_message: Error details if failed.
        processing_time_ms: Processing duration in milliseconds.
        processed_at: Processing timestamp.
    """

    __tablename__ = "processing_logs"
    __table_args__ = (
        Index("ix_log_document_id", "document_id"),
        Index("ix_log_status", "status"),
        Index("ix_log_processed_at", "processed_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: int
    document_title: Optional[str] = None
    status: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_response: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
