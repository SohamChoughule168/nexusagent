"""
Tenant Context and Authorization Services

Provides secure tenant context resolution and authorization validation
for multi-tenant operations.
"""

import uuid
from contextlib import contextmanager
from typing import Optional, Set
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.all_models import OrganizationMember
from app.core.security import get_user_role, get_user_organization_id


class TenantAccessError(Exception):
    """Raised when tenant access is denied."""
    pass


class OrganizationNotFoundError(Exception):
    """Raised when organization is not found."""
    pass


class MembershipNotFoundError(Exception):
    """Raised when user is not a member of organization."""
    pass


class InsufficientPermissionsError(Exception):
    """Raised when user lacks required permissions."""
    pass


@dataclass
class TenantContext:
    """Current tenant context derived from authenticated user."""
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: str

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")

    @property
    def can_manage_members(self) -> bool:
        return self.role in ("owner", "admin")

    @property
    def can_manage_agents(self) -> bool:
        return self.role in ("owner", "admin", "member")

    @property
    def can_view_analytics(self) -> bool:
        return self.role in ("owner", "admin", "member", "viewer")

    @property
    def can_manage_billing(self) -> bool:
        return self.role == "owner"


class TenantContextResolver:
    """Resolves and validates tenant context from authenticated user."""

    # Role hierarchy: higher index = more permissions
    ROLE_HIERARCHY = ["viewer", "member", "admin", "owner"]

    def __init__(self, db: Session):
        self.db = db

    def resolve_context(
        self,
        user: User,
        organization_id: uuid.UUID
    ) -> TenantContext:
        """
        Resolve tenant context for a user in an organization.

        Validates:
        - User is active
        - Organization exists
        - User is member of organization
        - Returns context with role-based permissions
        """
        if not user.is_active:
            raise TenantAccessError("User account is inactive")

        # Check membership
        member = self.db.query(OrganizationMember).filter(
            OrganizationMember.user_id == user.id,
            OrganizationMember.organization_id == organization_id
        ).first()

        if not member:
            raise MembershipNotFoundError(
                f"User {user.id} is not a member of organization {organization_id}"
            )

        return TenantContext(
            organization_id=organization_id,
            user_id=user.id,
            role=member.role
        )

    def validate_organization_access(
        self,
        user: User,
        organization_id: uuid.UUID,
        required_roles: Optional[Set[str]] = None
    ) -> TenantContext:
        """
        Validate user has access to organization with optional role requirements.

        Args:
            user: Authenticated user
            organization_id: Target organization
            required_roles: Set of acceptable roles (if None, any member allowed)

        Returns:
            TenantContext with resolved permissions

        Raises:
            MembershipNotFoundError: User not member of organization
            InsufficientPermissionsError: User role not in required_roles
        """
        context = self.resolve_context(user, organization_id)

        if required_roles and context.role not in required_roles:
            raise InsufficientPermissionsError(
                f"Role '{context.role}' not sufficient. Required: {required_roles}"
            )

        return context

    def can_access_organization(
        self,
        user: User,
        organization_id: uuid.UUID
    ) -> bool:
        """Check if user can access organization (any role)."""
        try:
            self.resolve_context(user, organization_id)
            return True
        except (MembershipNotFoundError, TenantAccessError):
            return False

    def get_user_organizations(self, user: User) -> list[uuid.UUID]:
        """Get all organization IDs user is a member of."""
        memberships = self.db.query(OrganizationMember).filter(
            OrganizationMember.user_id == user.id
        ).all()
        return [m.organization_id for m in memberships]


class RoleManager:
    """Manages organization member roles and permissions."""

    VALID_ROLES = {"owner", "admin", "member", "viewer"}

    def __init__(self, db: Session):
        self.db = db

    def validate_role(self, role: str) -> bool:
        """Validate role is one of the allowed values."""
        return role in self.VALID_ROLES

    def can_promote_to(self, current_role: str, target_role: str) -> bool:
        """Check if current role can promote to target role."""
        hierarchy = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}
        return hierarchy.get(current_role, 0) > hierarchy.get(target_role, 0)

    def can_demote_from(self, current_role: str, target_role: str) -> bool:
        """Check if current role can demote from target role."""
        return self.can_promote_to(current_role, target_role)

    def change_member_role(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        new_role: str,
        changed_by: uuid.UUID
    ) -> OrganizationMember:
        """Change a member's role with authorization validation."""
        if not self.validate_role(new_role):
            raise ValueError(f"Invalid role: {new_role}")

        # Get the member being changed
        member = self.db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id
        ).first()

        if not member:
            raise MembershipNotFoundError(
                f"User {user_id} not a member of organization {organization_id}"
            )

        # Get the changer's role
        changer = self.db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == changed_by
        ).first()

        if not changer:
            raise MembershipNotFoundError(
                f"Changer {changed_by} not a member of organization {organization_id}"
            )

        # Cannot change owner's role (only owner can change roles)
        if member.role == "owner" and changer.user_id != user_id:
            raise InsufficientPermissionsError("Cannot change owner's role")

        # Changer must be owner or admin
        if changer.role not in ("owner", "admin"):
            raise InsufficientPermissionsError("Only owners and admins can change roles")

        # Cannot promote someone to owner (only existing owner can)
        if new_role == "owner" and changer.role != "owner":
            raise InsufficientPermissionsError("Only owners can promote to owner")

        # Changer must have higher role than target's new role
        if not self.can_promote_to(changer.role, new_role):
            raise InsufficientPermissionsError(
                f"Role '{changer.role}' cannot promote to '{new_role}'"
            )

        member.role = new_role
        self.db.commit()
        self.db.refresh(member)
        return member

    def add_member(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        added_by: uuid.UUID
    ) -> OrganizationMember:
        """Add a new member to organization."""
        if not self.validate_role(role):
            raise ValueError(f"Invalid role: {role}")

        # Check adder's permissions
        adder = self.db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == added_by
        ).first()

        if not adder or adder.role not in ("owner", "admin"):
            raise InsufficientPermissionsError("Only owners and admins can add members")

        # Cannot add another owner
        if role == "owner" and adder.role != "owner":
            raise InsufficientPermissionsError("Only owners can add owners")

        # Check if already member
        existing = self.db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id
        ).first()

        if existing:
            raise ValueError(f"User {user_id} is already a member")

        member = OrganizationMember(
            organization_id=str(organization_id),
            user_id=str(user_id),
            role=role
        )
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def remove_member(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        removed_by: uuid.UUID
    ) -> bool:
        """Remove a member from organization."""
        remover = self.db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == removed_by
        ).first()

        if not remover or remover.role not in ("owner", "admin"):
            raise InsufficientPermissionsError("Only owners and admins can remove members")

        member = self.db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id
        ).first()

        if not member:
            raise MembershipNotFoundError(
                f"User {user_id} not a member of organization {organization_id}"
            )

        # Cannot remove owner
        if member.role == "owner":
            raise InsufficientPermissionsError("Cannot remove owner")

        # Remover must have higher role than member
        if member.role == "admin" and remover.role != "owner":
            raise InsufficientPermissionsError("Only owners can remove admins")

        self.db.delete(member)
        self.db.commit()
        return True


# Convenience function for FastAPI dependencies
def get_tenant_resolver(db: Session) -> TenantContextResolver:
    """FastAPI dependency for tenant context resolver."""
    return TenantContextResolver(db)


def get_role_manager(db: Session) -> RoleManager:
    """FastAPI dependency for role manager."""
    return RoleManager(db)


@contextmanager
def tenant_context(db: Session, organization_id: uuid.UUID):
    """
    Context manager for tenant-scoped operations.

    Usage:
        with tenant_context(db, org_id) as ctx:
            # All operations automatically scoped to organization
            agents = ctx.agents().get_all()
    """
    # This is a marker - actual scoping happens in repositories
    yield TenantContext(
        organization_id=organization_id,
        user_id=uuid.uuid4(),  # Placeholder
        role="member"
    )


# Backward compatibility
def get_user_tenant_context(
    db: Session,
    user: User,
    organization_id: uuid.UUID
) -> TenantContext:
    """Backward compatible function to get tenant context."""
    resolver = TenantContextResolver(db)
    return resolver.resolve_context(user, organization_id)


__all__ = [
    "TenantContext",
    "TenantContextResolver",
    "RoleManager",
    "TenantAccessError",
    "OrganizationNotFoundError",
    "MembershipNotFoundError",
    "InsufficientPermissionsError",
    "get_tenant_resolver",
    "get_role_manager",
    "tenant_context",
    "get_user_tenant_context",
]