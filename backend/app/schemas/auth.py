from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    organization_name: str
    organization_slug: str


class UserLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Dict[str, Any] = Field(default_factory=dict)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordChange(BaseModel):
    email: str
    current_password: str
    new_password: str


class APIKeyCreate(BaseModel):
    name: str
    scopes: List[str] = Field(default_factory=list)


class APIKeyInfo(BaseModel):
    """Non-secret representation of a stored API key (never exposes the key)."""

    id: str
    name: str
    key_prefix: str
    scopes: List[str] = Field(default_factory=list)
    rate_limit: Optional[int] = None
    is_active: bool = True
    created_at: Optional[Any] = None
    last_used_at: Optional[Any] = None


class APIKeyResponse(BaseModel):
    key: str
    key_prefix: str
    name: str
    scopes: List[str] = Field(default_factory=list)
