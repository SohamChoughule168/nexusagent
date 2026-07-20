"""Schemas for the webhook subscriptions API (Milestone B, Step 6)."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WebhookSubscriptionCreate(BaseModel):
    """Register a webhook subscription for a platform event type."""

    event_type: str = Field(..., min_length=1, max_length=50)
    url: str = Field(..., min_length=1, max_length=500)
    secret: Optional[str] = Field(None, description="HMAC-SHA256 signing secret")
    is_active: bool = True


class WebhookSubscriptionResponse(BaseModel):
    """A registered webhook subscription (secret is never returned)."""

    id: UUID
    organization_id: UUID
    event_type: str
    url: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryResponse(BaseModel):
    """The outcome of delivering an event to a subscription."""

    id: UUID
    subscription_id: UUID
    event_type: str
    status: str
    response_status: Optional[int] = None
    attempt_count: int
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
