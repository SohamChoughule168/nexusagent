import uuid
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime

class AgentBase(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: str
    welcome_message: Optional[str] = None
    model_provider: Optional[str] = "openrouter"
    model_name: Optional[str] = "anthropic/claude-3.5-sonnet"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None

class AgentCreate(AgentBase):
    public_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    welcome_message: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    status: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    knowledge_base_ids: Optional[List[str]] = None
    enabled_tool_ids: Optional[List[str]] = None

class AgentSettingsResponse(BaseModel):
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    citation_config: Optional[Dict[str, Any]] = None
    fallback_behavior: Optional[str] = None
    max_response_length: Optional[int] = None
    tool_selection_strategy: Optional[str] = None
    response_tone: Optional[str] = None
    company_identity: Optional[Dict[str, Any]] = None

class AgentResponse(AgentBase):
    id: uuid.UUID
    public_id: str
    status: str
    config: Optional[Dict[str, Any]] = None
    knowledge_base_ids: Optional[List[str]] = None
    enabled_tool_ids: Optional[List[str]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AgentPlaygroundRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    stream: bool = True

class AgentPlaygroundResponse(BaseModel):
    response: str
    session_id: str
    citations: Optional[List[Dict[str, Any]]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    token_usage: Optional[Dict[str, int]] = None
    cost_usd: Optional[float] = None

class StringMap(BaseModel):
    key: str
    value: str

class Both(BaseModel):
    both: Dict[str, str] = {}