"""Schemas for retrieval-augmented generation (RAG) queries."""
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    """A question posed against a knowledge base."""

    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class RAGSource(BaseModel):
    """A retrieved chunk cited as a source for the answer."""

    chunk_id: UUID
    document_id: UUID
    score: float
    snippet: str


class RAGQueryResponse(BaseModel):
    """A grounded answer plus the sources it was derived from."""

    answer: str
    sources: List[RAGSource]
