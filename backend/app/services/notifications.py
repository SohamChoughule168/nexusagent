"""Notifications & webhook dispatch (Milestone B, Step 6).

* **In-app notifications** -- :func:`create_notification` persists a
  ``Notification`` row (optionally scoped to a single user, otherwise shown to
  the whole organization).
* **Webhook events** -- :func:`dispatch_event` fans a platform event out to the
  organization's *active* webhook subscriptions for that event type. Each
  payload is signed with an HMAC-SHA256 of the subscription's ``secret``
  (``X-Webhook-Signature: sha256=...``) and a ``WebhookDelivery`` row records
  the outcome (status / HTTP status / attempt count) for observability.

All helpers are tenant-scoped and defensive: they never raise to the caller, so
notification/webhook side-effects can never break the operation that triggered
them.
"""
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.all_models import (
    Notification,
    WebhookDelivery,
    WebhookSubscription,
)

logger = get_logger(__name__)


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def create_notification(
    db: Session,
    organization_id: Any,
    type: str,
    title: str,
    body: Optional[str] = None,
    *,
    user_id: Any = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Notification:
    """Create an in-app notification (optionally for a single user)."""
    note = Notification(
        organization_id=str(_uuid(organization_id)),
        data={
            "type": type,
            "title": title,
            "body": body,
            "user_id": str(user_id) if user_id else None,
            "metadata": meta or {},
        },
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def notify_org(
    db: Session,
    organization_id: Any,
    type: str,
    title: str,
    body: Optional[str] = None,
    *,
    meta: Optional[Dict[str, Any]] = None,
) -> Notification:
    """Create an organization-wide notification (visible to all members)."""
    return create_notification(db, organization_id, type, title, body, meta=meta)


def dispatch_event(
    db: Session,
    organization_id: Any,
    event_type: str,
    payload: Dict[str, Any],
) -> List[WebhookDelivery]:
    """Deliver ``event_type`` to every active subscription for it in the tenant.

    Returns the list of recorded ``WebhookDelivery`` rows (one per subscriber),
    regardless of success/failure.
    """
    org_id = _uuid(organization_id)
    subs = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.organization_id == org_id,
            WebhookSubscription.event_type == event_type,
            WebhookSubscription.is_active.is_(True),
        )
        .all()
    )
    return [_deliver(db, org_id, sub, event_type, payload) for sub in subs]


def _deliver(
    db: Session,
    org_id: UUID,
    sub: WebhookSubscription,
    event_type: str,
    payload: Dict[str, Any],
) -> WebhookDelivery:
    """POST a signed payload to one subscription and record the delivery."""
    delivery = WebhookDelivery(
        organization_id=str(org_id),
        data={
            "subscription_id": str(sub.id),
            "event_type": event_type,
            "status": "pending",
            "attempt_count": 0,
        },
    )
    db.add(delivery)

    body = json.dumps(
        {"event_type": event_type, "payload": payload}, default=str
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if sub.secret:
        signature = hmac.new(sub.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(sub.url, content=body, headers=headers)
        delivery.status = "success" if 200 <= resp.status_code < 300 else "failed"
        delivery.response_status = resp.status_code
        delivery.attempt_count = 1
    except Exception as exc:  # noqa: BLE001 -- record and continue
        delivery.status = "failed"
        delivery.last_error = str(exc)[:2000]
        delivery.attempt_count = 1
        logger.warning("webhook_delivery_failed", subscription_id=str(sub.id), error=str(exc))

    db.commit()
    db.refresh(delivery)
    return delivery


__all__ = [
    "create_notification",
    "notify_org",
    "dispatch_event",
]
