"""Audit-log API (Milestone B, Step 4 — audit visibility).

Exposes the immutable, tenant-scoped audit trail written by
``app.services.audit.record_audit``. Reads are restricted to owners and admins
of the organization (the audit log is an administrative surface), and every
query is filtered by ``organization_id`` derived from the authenticated
principal -- a member of another tenant can never read these rows.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context, require_roles
from app.core.database import get_db
from app.models.base import AuditLogModel
from app.schemas.audit import AuditLogList, AuditLogResponse
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/audit", tags=["audit"])


def _uuid_or_400(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field}: expected a valid UUID",
        )


@router.get(
    "/logs",
    response_model=AuditLogList,
)
def list_audit_logs(
    action: Optional[str] = Query(None, description="Filter by action (e.g. tool.register)"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    user_id: Optional[str] = Query(None, description="Filter by actor user id"),
    since: Optional[str] = Query(None, description="Only entries at/after this ISO-8601 timestamp"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant: TenantContext = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
):
    """List the organization's audit-log entries (newest first), tenant-scoped.

    Supports filtering by ``action``, ``resource_type``, ``user_id`` and a
    ``since`` ISO-8601 timestamp, plus ``limit`` / ``offset`` pagination. The
    response always includes the total count for the active filter set.
    """
    uid = None
    if user_id:
        uid = _uuid_or_400(user_id, "user_id")
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid 'since' timestamp (expected ISO-8601)",
            )

    base = select(AuditLogModel).where(
        AuditLogModel.organization_id == tenant.organization_id
    )
    if action:
        base = base.where(AuditLogModel.action == action)
    if resource_type:
        base = base.where(AuditLogModel.resource_type == resource_type)
    if uid is not None:
        base = base.where(AuditLogModel.user_id == uid)
    if since_dt is not None:
        base = base.where(AuditLogModel.created_at >= since_dt)

    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar() or 0

    rows = (
        db.execute(
            base.order_by(AuditLogModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return AuditLogList(
        items=[AuditLogResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
