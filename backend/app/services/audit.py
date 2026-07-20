"""Audit-trail recording (Milestone B, Step 4 — RBAC / audit visibility).

The ``audit_logs`` table and ``AuditLogModel`` already exist but were never
written to. This module is the single, defensive entry point for appending
audit entries. ``record`` never raises: a failure to persist an audit row is
logged and swallowed so it can never break the primary business operation it
observes.

Usage::

    from app.services.audit import record_audit
    record_audit(
        db, tenant.organization_id, "tool.register",
        user_id=tenant.user_id, resource_type="tool", resource_id=str(tool.id),
    )
"""
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.models.base import AuditLogModel

logger = get_logger(__name__)


def record_audit(
    db,
    organization_id: str,
    action: str,
    *,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[AuditLogModel]:
    """Append an immutable audit-log entry. Returns the row or ``None`` on error."""
    from uuid import UUID

    try:
        org_id = organization_id if isinstance(organization_id, UUID) else UUID(str(organization_id))
        entry = AuditLogModel(
            organization_id=org_id,
            action=action,
            resource_type=resource_type,
            resource_id=(UUID(str(resource_id)) if resource_id else None),
            user_id=(UUID(str(user_id)) if user_id else None),
            ip_address=ip_address,
            user_agent=user_agent,
            meta=meta or {},
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    except Exception as exc:  # noqa: BLE001 -- audit must never break the caller
        logger.warning("audit_record_failed", action=action, error=str(exc))
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
