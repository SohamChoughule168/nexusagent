import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.all_models import OrganizationMember
from app.core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Token settings
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using Argon2."""
    return pwd_context.hash(password)


def create_access_token(
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    expires_delta: timedelta = None
) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": str(user_id),
        "org": str(organization_id),
        "type": "access",
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm="HS256")
    return encoded_jwt


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Create a refresh token that only contains user ID."""
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    encoded_jwt = jwt.encode(to_encode, settings.JWT_REFRESH_SECRET_KEY, algorithm="HS256")
    return encoded_jwt


def decode_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT token."""
    try:
        secret_key = settings.JWT_SECRET_KEY if token_type == "access" else settings.JWT_REFRESH_SECRET_KEY
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])

        # Validate token type
        if payload.get("type") != token_type:
            return None

        # Check expiration
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            return None

        return payload

    except JWTError:
        return None


def get_user_from_token(db: Session, token: str) -> Optional[User]:
    """Get the user associated with a token."""
    payload = decode_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    from app.models.user import User
    return db.query(User).filter(User.id == uuid.UUID(user_id)).first()


def get_user_organization_id(db: Session, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Get the organization ID for a user (assumes single org membership for now)."""
    member = db.query(OrganizationMember).filter(
        OrganizationMember.user_id == user_id
    ).first()

    if not member:
        return None

    return member.organization_id


def get_user_role(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> Optional[str]:
    """Get the user's role in an organization."""
    member = db.query(OrganizationMember).filter(
        OrganizationMember.user_id == user_id,
        OrganizationMember.organization_id == organization_id
    ).first()

    if not member:
        return None

    return member.role


def hash_api_key(key: str) -> str:
    """Hash an API key for storage."""
    return pwd_context.hash(key)


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify an API key against its hash."""
    return pwd_context.verify(plain_key, hashed_key)


def generate_api_key() -> str:
    """Generate a secure random API key."""
    import secrets
    return f"nx_{secrets.token_urlsafe(32)}"


def get_key_prefix(key: str) -> str:
    """Get the first 8 characters of the key for identification."""
    return key[:8]