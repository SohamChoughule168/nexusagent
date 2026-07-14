from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class DocumentResponse(BaseModel):
    """Serialised document metadata as returned by the API.

    The ORM attribute is ``meta`` (``metadata`` is reserved by SQLAlchemy's
    declarative Base), so we map it to the conventional ``metadata`` JSON key
    via a validation/serialization alias.
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
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        alias="meta",
        validation_alias="meta",
        serialization_alias="metadata",
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
