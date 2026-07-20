"""Webhook subscriptions API (Milestone B, Step 6).

Manage an organization's webhook subscriptions and trigger a manual test
delivery. Subscriptions are tenant-scoped (``organization_id`` derived from the
principal). Event delivery (signed with HMAC-SHA256) is performed by
:func:`app.services.notifications.dispatch_event`; this module only manages the
subscriptions and exposes a manual test trigger.

Manager roles (owner/admin/member) may read; only owners/admins may create,
delete, or test (these are configuration changes).
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context, require_roles
from app.core.database import get_db
from app.models.all_models import WebhookSubscription
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.webhook import (
    WebhookDeliveryResponse,
    WebhookSubscriptionCreate,
    WebhookSubscriptionResponse,
)
from app.services.audit import record_audit
from app.services.notifications import dispatch_event
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_MANAGER_ROLES = ("owner", "admin")


def _uuid_or_400(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field}: expected a valid UUID",
        )


@router.post(
    "",
    response_model=WebhookSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_webhook(
    payload: WebhookSubscriptionCreate,
    tenant: TenantContext = Depends(require_roles(*_MANAGER_ROLES)),
    db: Session = Depends(get_db),
):
    """Register a webhook subscription for a platform event type."""
    sub = WebhookSubscription(
        organization_id=str(tenant.organization_id),
        data={
            "event_type": payload.event_type,
            "url": payload.url,
            "secret": payload.secret,
            "is_active": payload.is_active,
        },
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    record_audit(
        db, tenant.organization_id, "webhook.create",
        user_id=str(tenant.user_id), resource_type="webhook_subscription",
        resource_id=str(sub.id), meta={"event_type": payload.event_type},
    )
    return sub


@router.get("", response_model=List[WebhookSubscriptionResponse])
def list_webhooks(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List the organization's webhook subscriptions."""
    subs = (
        db.query(WebhookSubscription)
        .filter(WebhookSubscription.organization_id == tenant.organization_id)
        .order_by(WebhookSubscription.created_at.desc())
        .all()
    )
    return subs


@router.get("/{webhook_id}", response_model=WebhookSubscriptionResponse)
def get_webhook(
    webhook_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get a single webhook subscription by id (tenant-scoped)."""
    wid = _uuid_or_400(webhook_id, "webhook_id")
    sub = db.get(WebhookSubscription, wid)
    if sub is None or sub.organization_id != tenant.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return sub


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: str,
    tenant: TenantContext = Depends(require_roles(*_MANAGER_ROLES)),
    db: Session = Depends(get_db),
):
    """Delete a webhook subscription."""
    wid = _uuid_or_400(webhook_id, "webhook_id")
    sub = db.get(WebhookSubscription, wid)
    if sub is None or sub.organization_id != tenant.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    db.delete(sub)
    db.commit()
    record_audit(
        db, tenant.organization_id, "webhook.delete",
        user_id=str(tenant.user_id), resource_type="webhook_subscription",
        resource_id=str(wid),
    )


@router.post("/{webhook_id}/test", response_model=WebhookDeliveryResponse)
def test_webhook(
    webhook_id: str,
    tenant: TenantContext = Depends(require_roles(*_MANAGER_ROLES)),
    db: Session = Depends(get_db),
):
    """Trigger a manual test delivery of a sample event to this subscription."""
    wid = _uuid_or_400(webhook_id, "webhook_id")
    sub = db.get(WebhookSubscription, wid)
    if sub is None or sub.organization_id != tenant.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    deliveries = dispatch_event(
        db,
        tenant.organization_id,
        sub.event_type,
        {"test": True, "subscription_id": str(sub.id)},
    )
    delivery = deliveries[0] if deliveries else None
    if delivery is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Subscription is inactive or could not be delivered to",
        )
    return delivery
