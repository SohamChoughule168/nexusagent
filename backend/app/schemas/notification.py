"""Schemas for the notifications API (Milestone B, Step 6)."""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    """A single in-app notification."""

    id: UUID
    organization_id: UUID
    user_id: Optional[UUID] = None
    type: str
    title: str
    body: Optional[str] = None
    read: bool = False
    meta: Dict[str, Any] = {}
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
