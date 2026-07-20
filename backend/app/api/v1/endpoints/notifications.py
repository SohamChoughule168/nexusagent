"""In-app notifications API (Milestone B, Step 6).

List / read the organization's notifications. A member sees organization-wide
notifications (``user_id IS NULL``) plus their own; the ``unread`` filter scopes
to unread items and ``read-all`` marks the member's visible notifications read.

Tenant isolation is enforced via ``organization_id`` derived from the principal;
a member can never read another tenant's notifications.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context
from app.core.database import get_db
from app.models.all_models import Notification
from app.schemas.notification import NotificationResponse
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _visible_filter(stmt, org_id, user_id):
    """Scope notifications to org-wide + personal for the caller."""
    return stmt.where(
        Notification.organization_id == org_id,
    ).where(
        (Notification.user_id.is_(None)) | (Notification.user_id == user_id)
    )


@router.get("", response_model=List[NotificationResponse])
def list_notifications(
    unread: Optional[bool] = Query(None, description="Filter to unread/read items"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List the caller's visible notifications (org-wide + personal), newest first."""
    stmt = select(Notification)
    stmt = _visible_filter(stmt, tenant.organization_id, tenant.user_id)
    if unread is not None:
        stmt = stmt.where(Notification.read.is_(not unread))
    rows = (
        db.execute(stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return [NotificationResponse.model_validate(r) for r in rows]


@router.get("/unread-count", response_model=dict)
def unread_count(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Count the caller's unread notifications."""
    from sqlalchemy import func

    stmt = select(func.count()).select_from(Notification)
    stmt = _visible_filter(stmt, tenant.organization_id, tenant.user_id).where(
        Notification.read.is_(False)
    )
    total = db.execute(stmt).scalar() or 0
    return {"unread_count": int(total)}


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(
    notification_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Mark a notification read (only if visible to the caller)."""
    from uuid import UUID

    try:
        nid = UUID(notification_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid notification_id")

    note = db.get(Notification, nid)
    if note is None or note.organization_id != tenant.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    # Only the intended recipient (or an org-wide notice) is markable by this user.
    if note.user_id is not None and note.user_id != tenant.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    note.read = True
    db.commit()
    db.refresh(note)
    return NotificationResponse.model_validate(note)


@router.post("/read-all", response_model=dict)
def mark_all_read(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Mark all of the caller's visible notifications read."""
    from sqlalchemy import update

    stmt = (
        update(Notification)
        .where(Notification.organization_id == tenant.organization_id)
        .where((Notification.user_id.is_(None)) | (Notification.user_id == tenant.user_id))
        .where(Notification.read.is_(False))
        .values(read=True)
    )
    result = db.execute(stmt)
    db.commit()
    return {"marked_read": result.rowcount}
