from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class DocumentResponse(BaseModel):
    """Serialised document metadata as returned by the API.

    The ORM attribute is ``meta`` (``metadata`` is reserved by SQLAlchemy's
    declarative Base), so we map it to the conventional ``metadata`` JSON key
    via a validation/serialization alias.

    Milestone B fields (indexing progress + metadata tags) are surfaced so the
    UI can render real ingestion/embedding progress and support tag-based
    filtering at retrieval time.
    """

    id: UUID
    knowledge_base_id: UUID
    organization_id: UUID
    filename: str
    original_filename: str
    title: Optional[str] = None
    mime_type: str
    file_size: int
    storage_path: str
    status: str
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    error_message: Optional[str] = None
    upload_member_id: UUID
    embedding_id: Optional[str] = None
    # Milestone B: indexing progress + metadata filtering support.
    indexing_progress: int = 0
    total_chunks: int = 0
    indexed_chunks: int = 0
    last_indexed_at: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        alias="meta",
        validation_alias="meta",
        serialization_alias="metadata",
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentChunkResponse(BaseModel):
    """Serialised document chunk as returned by the API.

    The dense ``embedding`` vector is intentionally excluded from the response
    (it is large and only used server-side for similarity); ``embedding_id``
    identifies the stored vector instead.
    """

    id: UUID
    document_id: UUID
    knowledge_base_id: UUID
    organization_id: UUID
    chunk_index: int
    content: str
    token_count: Optional[int] = None
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    embedding_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        alias="meta",
        validation_alias="meta",
        serialization_alias="metadata",
    )
    # Present on retrieval/search responses: cosine similarity to the query.
    score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
