"""FastAPI authentication & authorization dependencies.

This module is the single integration point that turns a JWT bearer token
into a resolved tenant context for the rest of the API. It reuses the existing
security primitives (``app.core.security``) and the RBAC / tenant services
(``app.services.tenant_context``) so that:

* tenant isolation is enforced at the API boundary: every protected endpoint
  derives ``organization_id`` from the authenticated principal, never from
  request data; and
* role-based access control is available to every endpoint via
  ``require_roles(...)``.

No new auth logic is introduced here -- only the wiring between the already
tested primitives (token decode, password/key hashing, tenant resolution) and
FastAPI's dependency system.
"""
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.services.tenant_context import (
    MembershipNotFoundError,
    TenantAccessError,
    TenantContext,
    TenantContextResolver,
)

# ``auto_error=False`` so we can raise our own 401 with a WWW-Authenticate
# header instead of letting HTTPBearer short-circuit with a bare 403.
oauth2_scheme = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = {"WWW-Authenticate": "Bearer"}


@dataclass
class AuthenticatedPrincipal:
    """The authenticated caller derived from a valid access token."""

    user: User
    organization_id: uuid.UUID
    payload: dict


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedPrincipal:
    """Resolve the authenticated user from a Bearer access token.

    Raises 401 if the token is missing, malformed, expired, or references an
    unknown or inactive user.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers=_UNAUTHENTICATED,
        )

    token = credentials.credentials
    payload = decode_token(token, "access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers=_UNAUTHENTICATED,
        )

    user_id = payload.get("sub")
    org_id = payload.get("org")
    if not user_id or not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing required claims",
            headers=_UNAUTHENTICATED,
        )

    try:
        uid = uuid.UUID(user_id)
        oid = uuid.UUID(org_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token contains invalid claims",
            headers=_UNAUTHENTICATED,
        )

    user = db.query(User).filter(User.id == uid).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers=_UNAUTHENTICATED,
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers=_UNAUTHENTICATED,
        )

    return AuthenticatedPrincipal(user=user, organization_id=oid, payload=payload)


def get_tenant_context(
    principal: AuthenticatedPrincipal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Resolve the tenant context for the authenticated principal.

    Validates that the principal is still an active member of the
    organization claimed by the token. Raises 403 if membership is missing or
    the account is inactive at the tenant level.
    """
    resolver = TenantContextResolver(db)
    try:
        return resolver.resolve_context(principal.user, principal.organization_id)
    except (MembershipNotFoundError, TenantAccessError) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


def require_roles(*required_roles: str) -> Callable[..., TenantContext]:
    """RBAC dependency factory.

    Usage::

        @router.delete("/{public_id}")
        def delete(
            tenant: TenantContext = Depends(require_roles("owner", "admin")),
        ):
            ...

    Returns the ``TenantContext`` unchanged when the principal's role is in
    ``required_roles``; otherwise raises 403. When called with no roles, any
    authenticated member of the organization is permitted.
    """

    def _enforce(
        current_tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        if required_roles and current_tenant.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{current_tenant.role}' is not permitted; "
                    f"required one of {list(required_roles)}"
                ),
            )
        return current_tenant

    return _enforce


__all__ = [
    "AuthenticatedPrincipal",
    "oauth2_scheme",
    "get_current_user",
    "get_tenant_context",
    "require_roles",
]
