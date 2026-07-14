import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import Column, String, DateTime, Boolean, Text, Integer, Float, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import Base, MultiTenantModel


class KeyValueSettings(MultiTenantModel):
    """Generic key-value settings storage for organizational configuration."""
    __tablename__ = "organization_settings"
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), primary_key=True)
    key: str = Column(String(100), nullable=False)
    value: str = Column(String(255))

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('organization_id', 'key', name='unique_key_per_org'),
    )

    # Relationship
    organization = relationship("Organization", back_populates="settings_relationship")

    def __init__(self, organization_id: str, key: str, value: str):
        self.organization_id = uuid.UUID(organization_id)
        self.key = key
        self.value = value


class OrganizationMember(MultiTenantModel):
    __tablename__ = "organization_members"

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: str = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id: str = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    role: str = Column(String(20), nullable=False)  # 'owner', 'admin', 'member', 'viewer'
    joined_at: datetime = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="members")
    user = relationship("User", back_populates="organizations")

    __table_args__ = (
        UniqueConstraint('organization_id', 'user_id', name='unique_user_per_org'),
    )

    def __init__(self, organization_id: str, user_id: str, role: str = "member"):
        self.organization_id = uuid.UUID(organization_id)
        self.user_id = uuid.UUID(user_id)
        self.role = role


class SystemSettings(MultiTenantModel):
    __tablename__ = "system_settings"
    organization_id = Column(UUID(as_uuid=True), primary_key=True)
    theme: str = Column(String(20), default="system", nullable=False)  # 'system', 'light', 'dark'
    language: str = Column(String(10), default="en", nullable=False)
    timezone: str = Column(String(50), default="UTC", nullable=False)

    created_at: datetime = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __init__(self, organization_id: str):
        self.organization_id = uuid.UUID(organization_id)


class Agent(MultiTenantModel):
    __tablename__ = "agents"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True)
    organization_id: str = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    name: str = Column(String(255), nullable=False)
    description: Optional[str] = Column(Text)
    system_prompt: Text = Column(Text, nullable=False)
    welcome_message: Optional[str] = Column(Text)
    model_provider: str = Column(String(50), default="openrouter", nullable=False)
    model_name: str = Column(String(100), default="anthropic/claude-3.5-sonnet", nullable=False)
    temperature: float = Column(Integer, default=0)  # placeholder, should be Decimal
    max_tokens: Optional[int] = Column(Integer)
    top_p: Optional[float] = Column(Float())
    presence_penalty: Optional[float] = Column(Float())
    frequency_penalty: Optional[float] = Column(Float())
    status: str = Column(String(20), default="draft")  # 'draft', 'active', 'paused', 'archived'
    public_id: str = Column(String(50), unique=True)
    config: Dict[str, Any] = Column(JSONB, default=dict)
    created_at: datetime = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Optional[datetime] = Column(DateTime(timezone=True), onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="agents")
    conversations = relationship("Conversation", back_populates="agent")

    def __init__(self, organization_id: str, data: Dict[str, Any]):
        self.organization_id = uuid.UUID(organization_id)
        self.name = data.get("name", "")
        self.description = data.get("description", "")
        self.system_prompt = data.get("system_prompt", "")
        self.welcome_message = data.get("welcome_message", "")
        self.model_provider = data.get("model_provider", "openrouter")
        self.model_name = data.get("model_name", "anthropic/claude-3.5-sonnet")
        self.temperature = float(data.get("temperature", 0.7))
        self.max_tokens = data.get("max_tokens", None)
        self.top_p = data.get("top_p", None)
        self.presence_penalty = data.get("presence_penalty", None)
        self.frequency_penalty = data.get("frequency_penalty", None)
        self.status = data.get("status", "draft")
        self.public_id = data.get("public_id", str(uuid.uuid4())[:8])
        self.config = data.get("config", {})


class KnowledgeBase(MultiTenantModel):
    __tablename__ = "knowledge_bases"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: str = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    name: str = Column(String(255), nullable=False)
    description: Optional[str] = Column(Text)
    embedding_model: str = Column(String(100), default="text-embedding-3-small")
    chunk_size: int = Column(Integer, default=1000)
    chunk_overlap: int = Column(Integer, default=200)
    chunk_strategy: str = Column(String(50), default="recursive")
    retrieval_config: Dict[str, Any] = Column(JSONB, default=dict)

    # Relationships
    organization = relationship("Organization", back_populates="knowledge_bases")
    documents = relationship("Document", back_populates="knowledge_base")

    def __init__(self, organization_id: str, data: Dict[str, Any]):
        self.organization_id = uuid.UUID(organization_id)
        self.name = data.get("name", "")
        self.description = data.get("description", "")
        self.embedding_model = data.get("embedding_model", "text-embedding-3-small")
        self.chunk_size = data.get("chunk_size", 1000)
        self.chunk_overlap = data.get("chunk_overlap", 200)
        self.chunk_strategy = data.get("chunk_strategy", "recursive")
        self.retrieval_config = data.get("retrieval_config", {})


class Document(MultiTenantModel):
    __tablename__ = "documents"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id: str = Column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    organization_id: str = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    # ``filename`` is required by the live ``documents`` table (NOT NULL) and
    # stores the original upload name (the on-disk name lives in storage_path).
    filename: str = Column(String(255), nullable=False)
    original_filename: str = Column(String(255), nullable=False)
    title: Optional[str] = Column(String(255))
    mime_type: str = Column(String(100), nullable=False)
    file_size: int = Column(Integer, nullable=False)
    storage_path: str = Column(String(500), nullable=False)
    status: str = Column(String(20), default="uploaded", nullable=False)
    page_count: int = Column(Integer, default=0)
    chunk_count: int = Column(Integer, default=0)
    error_message: Optional[str] = Column(Text)
    # NOTE: the attribute is named ``meta`` (not ``metadata``) because
    # ``metadata`` is reserved by SQLAlchemy's declarative Base.
    meta: Dict[str, Any] = Column("metadata", JSONB, default=dict)
    upload_member_id: str = Column(UUID(as_uuid=True), nullable=False)  # Reference to User.id

    # Relationships
    organization = relationship("Organization", back_populates="documents")
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    document_chunks = relationship("DocumentChunk", back_populates="document")

    def __init__(self, organization_id, data: Dict[str, Any]):
        org_id = organization_id if isinstance(organization_id, uuid.UUID) else uuid.UUID(str(organization_id))
        self.organization_id = org_id
        self.knowledge_base_id = uuid.UUID(str(data.get("knowledge_base_id")))
        self.filename = data.get("filename") or data.get("original_filename", "")
        self.original_filename = data.get("original_filename", "")
        self.title = data.get("title")
        self.mime_type = data.get("mime_type", "")
        self.file_size = int(data.get("file_size") or 0)
        self.storage_path = data.get("storage_path", "")
        self.status = data.get("status", "uploaded")
        self.error_message = data.get("error_message")
        self.meta = data.get("metadata") or {}
        up = data.get("upload_member_id")
        self.upload_member_id = uuid.UUID(str(up)) if up else None


class DocumentChunk(MultiTenantModel):
    __tablename__ = "document_chunks"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True)
    document_id: str = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    knowledge_base_id: str = Column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    organization_id: str = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    chunk_index: int = Column(Integer, nullable=False)
    content: str = Column(Text, nullable=False)
    token_count: int = Column(Integer, default=0)
    page_number: int = Column(Integer)
    section_title: Optional[str] = Column(String(500))
    embedding_id: Optional[str] = Column(String(255))
    meta: Dict[str, Any] = Column("metadata", JSONB, default=dict)

    # Relationships
    document = relationship("Document", back_populates="document_chunks")

    def __init__(self, document_id: str, knowledge_base_id: str, organization_id: str, chunk_index: int,
                 content: str, metadata: Dict[str, Any] = None):
        self.document_id = uuid.UUID(document_id)
        self.knowledge_base_id = uuid.UUID(knowledge_base_id)
        self.organization_id = uuid.UUID(organization_id)
        self.chunk_index = chunk_index
        self.content = content
        self.token_count = len(self.content.split()) if self.content else 0
        self.page_number = metadata.get("page_number") if metadata else None
        self.section_title = metadata.get("section_title") if metadata else None
        self.embedding_id = metadata.get("embedding_id") if metadata else None
        self.meta = metadata or {}


class Conversation(MultiTenantModel):
    __tablename__ = "conversations"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True)
    organization_id: str = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    agent_id: str = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True)
    session_id: str = Column(String(255), nullable=False, unique=True)
    user_identifier: str = Column(String(255))  # Could be email or anonymous ID
    user_metadata: Dict[str, Any] = Column(JSONB, default=dict)
    summary: Optional[str] = Column(Text)
    message_count: int = Column(Integer, default=0)
    total_tokens: int = Column(Integer, default=0)
    total_cost_usd: float = Column(Float(), default=0.0)
    started_at: datetime = Column(DateTime(timezone=True), default=datetime.utcnow)
    closed_at: Optional[datetime] = Column(DateTime(timezone=True))
    status: str = Column(String(20), default="active")  # 'active', 'closed', 'escalated', 'archived'
    created_at: datetime = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Optional[datetime] = Column(DateTime(timezone=True), onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="conversations")
    agent = relationship("Agent", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")


class Message(MultiTenantModel):
    __tablename__ = "messages"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True)
    conversation_id: str = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)
    organization_id: str = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    role: str = Column(String(20), nullable=False)  # 'user', 'assistant', 'system', 'tool'
    content: str = Column(Text, nullable=False)
    token_count: int = Column(Integer, default=0)
    citations: Dict[str, Any] = Column(JSONB, default=dict)
    tool_calls: Dict[str, Any] = Column(JSONB, default=dict)
    tool_results: Dict[str, Any] = Column(JSONB, default=dict)
    model_provider: str = Column(String(50))
    model_name: str = Column(String(100))
    cost_usd: float = Column(Float(), default=0.0)
    created_at: datetime = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    def __init__(self, conversation_id: str, organization_id: str, role: str, content: str,
                 token_count: int = 0, citations=None, tool_calls=None, tool_results=None,
                 model_provider=None, model_name=None, cost_usd=0.0):
        self.conversation_id = uuid.UUID(conversation_id)
        self.organization_id = uuid.UUID(organization_id)
        self.role = role
        self.content = content
        self.token_count = token_count
        self.citations = citations or {}
        self.tool_calls = tool_calls or {}
        self.tool_results = tool_results or {}
        self.model_provider = model_provider
        self.model_name = model_name
        self.cost_usd = cost_usd


class Lead(MultiTenantModel):
    __tablename__ = "leads"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True)
    organization_id: str = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    agent_id: Optional[str] = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True, index=True)
    conversation_id: Optional[str] = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True, index=True)
    name: str = Column(String(255))
    email: str = Column(String(255))
    phone: str = Column(String(50))
    message: str = Column(Text)
    source: str = Column(String(100))  # 'widget', 'api', 'manual', etc.
    status: str = Column(String(50), default="new")  # 'new', 'contacted', 'qualified', 'lost'
    meta: Dict[str, Any] = Column("metadata", JSONB, default=dict)
    created_at: datetime = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Optional[datetime] = Column(DateTime(timezone=True), onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="leads")

    def __init__(self, organization_id: str, data: Dict[str, Any]):
        self.organization_id = uuid.UUID(organization_id)
        self.agent_id = uuid.UUID(data.get("agent_id", "")) if data.get("agent_id") else None
        self.conversation_id = uuid.UUID(data.get("conversation_id", "")) if data.get("conversation_id") else None
        self.name = data.get("name", "")
        self.email = data.get("email", "")
        self.phone = data.get("phone", "")
        self.message = data.get("message", "")
        self.source = data.get("source", "")
        self.status = data.get("status", "new")
        self.meta = data.get("metadata", {})


class APIRequest(Base):
    """Generic request schema for incoming API calls."""
    __abstract__ = True

    @classmethod
    def build_from_request(cls, request_dict: Dict[str, Any]):
        """Build a typed model from raw request data."""
        obj = cls()
        for key, value in request_dict.items():
            setattr(obj, key, value)
        return obj


class ToolConfig(MultiTenantModel):
    """Configuration for tools (webhook URLs, field definitions, etc.)."""
    __tablename__ = "tool_configs"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True)
    organization_id: str = Column(UUID(as_uuid=True), nullable=False, index=True)
    tool_name: str = Column(String(100), nullable=False)  # tool ID
    config_type: str = Column(String(50), nullable=False)  # 'webhook', 'custom', etc.
    config_data: Dict[str, Any] = Column(JSONB, default=dict)

    created_at: datetime = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __init__(self, organization_id: str, tool_name: str, config_data: Dict[str, Any]):
        self.organization_id = uuid.UUID(organization_id)
        self.tool_name = tool_name
        self.config_data = config_data


class UsageEvent(MultiTenantModel):
    """Track usage events for analytics and billing."""
    __tablename__ = "usage_events"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True)
    organization_id: str = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    agent_id: Optional[str] = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True, index=True)
    conversation_id: Optional[str] = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True, index=True)

    # Relationships
    organization = relationship("Organization", back_populates="usage_events")
    event_type: str = Column(String(50), nullable=False)  # 'chat_message', 'embedding_generation', 'tool_execution', etc.
    model_provider: str = Column(String(50))
    model_name: str = Column(String(100))
    input_tokens: int = Column(Integer, default=0)
    output_tokens: int = Column(Integer, default=0)
    total_tokens: int = Column(Integer, default=0)
    cost_usd: float = Column(Float(), default=0.0)
    meta: Dict[str, Any] = Column("metadata", JSONB, default=dict)
    created_at: datetime = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __init__(self, organization_id: str, data: Dict[str, Any]):
        self.organization_id = uuid.UUID(organization_id)
        self.agent_id = uuid.UUID(data.get("agent_id", "")) if data.get("agent_id") else None
        self.conversation_id = uuid.UUID(data.get("conversation_id", "")) if data.get("conversation_id") else None
        self.event_type = data.get("event_type", "")
        self.model_provider = data.get("model_provider", "")
        self.model_name = data.get("model_name", "")
        self.input_tokens = data.get("input_tokens", 0)
        self.output_tokens = data.get("output_tokens", 0)
        self.total_tokens = data.get("total_tokens", 0)
        self.cost_usd = data.get("cost_usd", 0.0)
        self.meta = data.get("metadata", {})


class APIKey(MultiTenantModel):
    """Hashed API key for programmatic access (key_hash never returned)."""
    __tablename__ = "api_keys"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    name: str = Column(String(255), nullable=False)
    key_hash: str = Column(String(255), nullable=False)
    key_prefix: str = Column(String(20), nullable=False, index=True)
    scopes: Dict[str, Any] = Column(JSONB, default=dict)
    rate_limit: Optional[int] = Column(Integer, default=100)
    last_used_at: Optional[datetime] = Column(DateTime(timezone=True))
    expires_at: Optional[datetime] = Column(DateTime(timezone=True))
    is_active: bool = Column(Boolean, default=True, nullable=False)
    created_at: datetime = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    organization = relationship(
        "Organization",
        back_populates="api_keys"
    )