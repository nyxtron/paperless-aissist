from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class Config(SQLModel, table=True):
    __tablename__ = "config"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value: str
    description: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    prompt_type: str = Field(default="classify")
    document_type_filter: Optional[str] = None
    system_prompt: str
    user_template: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProcessingLog(SQLModel, table=True):
    __tablename__ = "processing_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: int
    document_title: Optional[str] = None
    status: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_response: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None
    processed_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentTypeCache(SQLModel, table=True):
    __tablename__ = "document_type_cache"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    paperless_id: int
    name: str
    cached_at: datetime = Field(default_factory=datetime.utcnow)


class CorrespondentCache(SQLModel, table=True):
    __tablename__ = "correspondent_cache"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    paperless_id: int
    name: str
    cached_at: datetime = Field(default_factory=datetime.utcnow)


class TagCache(SQLModel, table=True):
    __tablename__ = "tag_cache"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    paperless_id: int
    name: str
    cached_at: datetime = Field(default_factory=datetime.utcnow)
