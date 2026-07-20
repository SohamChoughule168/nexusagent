"""Schemas for the audit-log API (Milestone B, Step 4 — audit visibility)."""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    """A single immutable audit-trail entry (read-only)."""

    id: UUID
    organization_id: UUID
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    meta: Dict[str, Any] = {}
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AuditLogList(BaseModel):
    """A page of audit-log entries."""

    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int
