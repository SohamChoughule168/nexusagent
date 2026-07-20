"""Schemas for organization membership / role management (Milestone B, Step 4)."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MemberResponse(BaseModel):
    """A member of the authenticated organization with their user profile."""

    user_id: UUID
    email: str
    full_name: Optional[str] = None
    role: str
    joined_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class AddMemberRequest(BaseModel):
    """Add an existing user (by email) to the organization."""

    email: str = Field(..., min_length=3, max_length=255)
    role: str = Field("member", pattern="^(owner|admin|member|viewer)$")


class ChangeRoleRequest(BaseModel):
    """Change a member's role within the organization."""

    role: str = Field(..., pattern="^(owner|admin|member|viewer)$")
