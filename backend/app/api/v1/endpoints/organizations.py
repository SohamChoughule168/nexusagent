"""Organization membership & role-management API (Milestone B, Step 4 — RBAC).

Admin capabilities on top of the existing tenant-isolation + role primitives:

* **List members** — any authenticated member of the organization.
* **Add member** — owners/admins add an *existing* user (by email) to the org.
* **Change role** — owners/admins promote/demote a member. Authorization rules
  (cannot demote the owner, only owners promote to owner, etc.) are enforced by
  the existing ``RoleManager`` so this endpoint never re-implements them.
* **Remove member** — owners/admins remove a member (never the owner).

Every mutation is tenant-scoped (``organization_id`` derived from the principal)
and recorded to the audit trail. The ``RoleManager`` raises typed exceptions on
invalid transitions; they are mapped to 400/403/404 here.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context, require_roles
from app.core.database import get_db
from app.models.user import User
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.organization import (
    AddMemberRequest,
    ChangeRoleRequest,
    MemberResponse,
)
from app.services.audit import record_audit
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/organizations", tags=["organizations"])

_VALID_ROLES = {"owner", "admin", "member", "viewer"}


def _uuid_or_400(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field}: expected a valid UUID",
        )


def _to_member_response(member, user: User) -> MemberResponse:
    return MemberResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
        joined_at=member.joined_at,
        is_active=user.is_active,
    )


@router.get("/members", response_model=List[MemberResponse])
def list_members(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List the organization's members with their user profiles."""
    repo = RepositoryFactory(db, tenant.organization_id).organization_members()
    rows = repo.get_members_with_users()
    return [_to_member_response(m, u) for m, u in rows]


@router.post(
    "/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    payload: AddMemberRequest,
    tenant: TenantContext = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Add an existing user (by email) to the organization."""
    from app.services.tenant_context import RoleManager
    from app.services.tenant_context import MembershipNotFoundError, InsufficientPermissionsError

    user_repo = RepositoryFactory(db, tenant.organization_id).users()
    user = user_repo.get_by_email(payload.email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user with that email exists",
        )

    manager = RoleManager(db)
    try:
        member = manager.add_member(
            organization_id=tenant.organization_id,
            user_id=user.id,
            role=payload.role,
            added_by=tenant.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except InsufficientPermissionsError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    record_audit(
        db, tenant.organization_id, "org.member_add",
        user_id=str(tenant.user_id), resource_type="user", resource_id=str(user.id),
        meta={"role": payload.role},
    )
    return _to_member_response(member, user)


@router.put("/members/{user_id}/role", response_model=MemberResponse)
def change_member_role(
    user_id: str,
    payload: ChangeRoleRequest,
    tenant: TenantContext = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Change a member's role (authorization enforced by ``RoleManager``)."""
    from app.services.tenant_context import RoleManager
    from app.services.tenant_context import (
        MembershipNotFoundError,
        InsufficientPermissionsError,
    )

    uid = _uuid_or_400(user_id, "user_id")
    manager = RoleManager(db)
    try:
        member = manager.change_member_role(
            organization_id=tenant.organization_id,
            user_id=uid,
            new_role=payload.role,
            changed_by=tenant.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except MembershipNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InsufficientPermissionsError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    user = db.query(User).filter(User.id == uid).first()
    record_audit(
        db, tenant.organization_id, "org.member_role_change",
        user_id=str(tenant.user_id), resource_type="user", resource_id=str(uid),
        meta={"new_role": payload.role},
    )
    return _to_member_response(member, user)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: str,
    tenant: TenantContext = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Remove a member from the organization (never the owner)."""
    from app.services.tenant_context import RoleManager
    from app.services.tenant_context import (
        MembershipNotFoundError,
        InsufficientPermissionsError,
    )

    uid = _uuid_or_400(user_id, "user_id")
    manager = RoleManager(db)
    try:
        manager.remove_member(
            organization_id=tenant.organization_id,
            user_id=uid,
            removed_by=tenant.user_id,
        )
    except MembershipNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InsufficientPermissionsError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    record_audit(
        db, tenant.organization_id, "org.member_remove",
        user_id=str(tenant.user_id), resource_type="user", resource_id=str(uid),
    )
    return None
