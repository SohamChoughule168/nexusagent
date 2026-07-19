from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    get_key_prefix,
    get_user_from_token,
    get_user_organization_id,
    get_user_role,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.auth_dependencies import (
    get_tenant_context,
    get_current_user,
    AuthenticatedPrincipal,
    TenantContext,
)
from app.repositories.tenant_repository import RepositoryFactory
from app.models.user import User
from app.models.organization import Organization
from app.models.all_models import OrganizationMember, APIKey
from app.schemas.auth import (
    TokenResponse,
    UserRegister,
    UserLogin,
    RefreshTokenRequest,
    PasswordChange,
    APIKeyCreate,
    APIKeyInfo,
    APIKeyResponse,
    APIKeyList,
    MessageResponse,
)
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/auth", tags=["auth"])

logger = get_logger(__name__)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """Register a new user and create an organization."""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # The organization slug is globally unique; surface a friendly 409 (not a
    # 500 from an IntegrityError) when it collides with an existing org.
    existing_org = db.query(Organization).filter(
        Organization.slug == user_data.organization_slug
    ).first()
    if existing_org:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already in use",
        )

    # Create organization
    org = Organization(
        name=user_data.organization_name,
        slug=user_data.organization_slug,
        plan="starter",
    )
    db.add(org)
    db.flush()  # Get the ID

    # Create user
    user = User(
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        email_verified=True,
    )
    db.add(user)
    db.flush()

    # Create organization membership (owner)
    member = OrganizationMember(
        organization_id=str(org.id),
        user_id=str(user.id),
        role="owner",
    )
    db.add(member)

    # Create default knowledge base
    from app.models.all_models import KnowledgeBase
    kb = KnowledgeBase(
        organization_id=str(org.id),
        data={
            "name": "Default Knowledge Base",
            "description": "Default knowledge base for your organization",
        },
    )
    db.add(kb)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration failed: a unique value conflicts with an existing record",
        )
    db.refresh(user)
    db.refresh(org)

    logger.info(
        "user_registered",
        user_id=str(user.id),
        organization_id=str(org.id),
        email=user.email,
        role="owner",
    )

    # Generate tokens
    access_token = create_access_token(user.id, org.id)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "organization_id": str(org.id),
            "organization_name": org.name,
            "role": "owner",
        }
    )


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Authenticate user and return tokens."""
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        logger.warning(
            "login_failed",
            email=form_data.username,
            reason="invalid_credentials",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Get user's organization (first one for now)
    member = db.query(OrganizationMember).filter(
        OrganizationMember.user_id == user.id
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a member of any organization",
        )

    org = db.query(Organization).filter(Organization.id == member.organization_id).first()

    logger.info(
        "user_login",
        user_id=str(user.id),
        organization_id=str(org.id),
        email=user.email,
        role=member.role,
    )

    # Update last login
    from datetime import datetime
    user.last_login_at = datetime.utcnow()
    db.commit()

    access_token = create_access_token(user.id, org.id)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "organization_id": str(org.id),
            "organization_name": org.name,
            "role": member.role,
        }
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Refresh access token using refresh token."""
    payload = decode_token(request.refresh_token, "refresh")

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")
    user = get_user_from_token(db, request.refresh_token)

    if not user or str(user.id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Get organization
    org_id = get_user_organization_id(db, user.id)
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no organization",
        )

    access_token = create_access_token(user.id, org_id)
    new_refresh_token = create_refresh_token(user.id)

    member = db.query(OrganizationMember).filter(
        OrganizationMember.user_id == user.id,
        OrganizationMember.organization_id == org_id
    ).first()

    org = db.query(Organization).filter(Organization.id == org_id).first()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        user={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "organization_id": str(org_id),
            "organization_name": org.name if org else "",
            "role": member.role if member else "member",
        }
    )


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    request: PasswordChange,
    current_user: AuthenticatedPrincipal = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the authenticated user's password.

    Requires a valid Bearer session — the target user is derived from the
    access token, never from a request body field. The current password is
    verified before the update, so the account-takeover surface is limited to
    an attacker who already holds a live session for the account (K1).
    """
    if not verify_password(request.current_password, current_user.user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.user.password_hash = get_password_hash(request.new_password)
    db.commit()

    logger.info("password_changed", user_id=str(current_user.user.id))
    return MessageResponse(message="Password changed successfully")


# API Key endpoints
@router.post("/api-keys", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    request: APIKeyCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Create a new API key for the authenticated organization.

    The plaintext key is returned exactly once (in the response). Only its hash
    is persisted; the ``key_hash`` is never returned on subsequent reads.
    """
    plain_key = generate_api_key()
    key_hash = hash_api_key(plain_key)
    key_prefix = get_key_prefix(plain_key)

    api_key = APIKey(
        organization_id=tenant.organization_id,
        name=request.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes={scope: True for scope in request.scopes},
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    logger.info("api_key_created", organization_id=str(tenant.organization_id), name=request.name)

    return APIKeyResponse(
        key=plain_key,
        key_prefix=key_prefix,
        name=request.name,
        scopes=request.scopes,
    )


@router.get("/api-keys", response_model=APIKeyList)
def list_api_keys(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List API keys for the authenticated organization.

    Returns non-secret metadata only — the hashed key is never exposed.
    """
    keys = (
        db.query(APIKey)
        .filter(APIKey.organization_id == tenant.organization_id)
        .order_by(APIKey.created_at.desc())
        .all()
    )
    return APIKeyList(
        keys=[
            APIKeyInfo(
                id=str(k.id),
                name=k.name,
                key_prefix=k.key_prefix,
                scopes=list(k.scopes.keys()) if isinstance(k.scopes, dict) else [],
                rate_limit=k.rate_limit,
                is_active=k.is_active,
                created_at=k.created_at,
                last_used_at=k.last_used_at,
            )
            for k in keys
        ]
    )