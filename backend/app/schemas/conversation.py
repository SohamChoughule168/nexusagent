import uuid
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime


class ConversationBase(BaseModel):
    agent_id: str
    user_identifier: Optional[str] = None
    user_metadata: Optional[Dict[str, Any]] = None
    status: Optional[str] = "active"


class ConversationCreate(ConversationBase):
    session_id: str


class ConversationUpdate(BaseModel):
    user_identifier: Optional[str] = None
    user_metadata: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    status: Optional[str] = None


class MessageNested(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    token_count: int = 0
    citations: Optional[Dict[str, Any]] = None
    tool_calls: Optional[Dict[str, Any]] = None
    tool_results: Optional[Dict[str, Any]] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    cost_usd: float = 0.0
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationResponse(ConversationBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    agent_id: uuid.UUID
    session_id: str
    summary: Optional[str] = None
    message_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    started_at: datetime
    closed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    messages: List[MessageNested] = []

    class Config:
        from_attributes = True


class MessageBase(BaseModel):
    role: str
    content: str


class MessageCreate(MessageBase):
    conversation_id: Optional[str] = None
    token_count: int = 0
    citations: Optional[Dict[str, Any]] = None
    tool_calls: Optional[Dict[str, Any]] = None
    tool_results: Optional[Dict[str, Any]] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    cost_usd: float = 0.0


class MessageResponse(MessageBase):
    id: uuid.UUID
    conversation_id: uuid.UUID
    organization_id: uuid.UUID
    token_count: int = 0
    citations: Optional[Dict[str, Any]] = None
    tool_calls: Optional[Dict[str, Any]] = None
    tool_results: Optional[Dict[str, Any]] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    cost_usd: float = 0.0
    created_at: datetime

    class Config:
        from_attributes = True
