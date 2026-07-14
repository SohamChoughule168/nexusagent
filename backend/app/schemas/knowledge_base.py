from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field
from datetime import datetime


class KnowledgeBaseBase(BaseModel):
    """Shared fields for knowledge base schemas."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    chunk_strategy: str = "recursive"
    retrieval_config: Optional[Dict[str, Any]] = None


class KnowledgeBaseCreate(KnowledgeBaseBase):
    """Payload for creating a knowledge base."""


class KnowledgeBaseUpdate(BaseModel):
    """Payload for updating a knowledge base (all fields optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    embedding_model: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    chunk_strategy: Optional[str] = None
    retrieval_config: Optional[Dict[str, Any]] = None


class KnowledgeBaseResponse(KnowledgeBaseBase):
    """Serialised knowledge base as returned by the API."""

    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
