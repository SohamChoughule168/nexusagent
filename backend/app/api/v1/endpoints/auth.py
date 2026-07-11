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
from app.repositories.tenant_repository import RepositoryFactory
from app.models.user import User
from app.models.organization import Organization
from app.models.all_models import OrganizationMember
from app.schemas.auth import (
    TokenResponse,
    UserRegister,
    UserLogin,
    RefreshTokenRequest,
    PasswordChange,
    APIKeyCreate,
    APIKeyResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


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
        organization_id=org.id,
        user_id=user.id,
        role="owner",
    )
    db.add(member)

    # Create default knowledge base
    from app.models.all_models import KnowledgeBase
    kb = KnowledgeBase(
        organization_id=org.id,
        name="Default Knowledge Base",
        description="Default knowledge base for your organization",
        default=True,
    )
    db.add(kb)

    db.commit()
    db.refresh(user)
    db.refresh(org)

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


@router.post("/change-password")
def change_password(request: PasswordChange, db: Session = Depends(get_db)):
    """Change user password."""
    # Get current user from token (would need auth dependency)
    # For now, we'll accept email + current password
    user = db.query(User).filter(User.email == request.email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    user.password_hash = get_password_hash(request.new_password)
    db.commit()

    return {"message": "Password changed successfully"}


# API Key endpoints
@router.post("/api-keys", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    request: APIKeyCreate,
    db: Session = Depends(get_db),
    # TODO: Add auth dependency
):
    """Create a new API key for the organization."""
    # TODO: Get organization_id from authenticated user
    organization_id = request.organization_id

    # Generate key
    plain_key = generate_api_key()
    key_hash = hash_api_key(plain_key)
    key_prefix = get_key_prefix(plain_key)

    # TODO: Save to database
    # For now, return the key (in production, only return it once!)
    return APIKeyResponse(
        key=plain_key,
        key_prefix=key_prefix,
        name=request.name,
        scopes=request.scopes,
    )


@router.get("/api-keys")
def list_api_keys(db: Session = Depends(get_db)):
    """List API keys for the organization."""
    # TODO: Implement with auth dependency
    return {"keys": []}


# Dependencies for auth
def get_current_user(token: str = Depends(None), db: Session = Depends(get_db)) -> User:
    """Get current user from access token."""
    # This would be a proper dependency in production
    pass