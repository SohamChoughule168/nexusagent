import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import MultiTenantModel


class Organization(MultiTenantModel):
    __tablename__ = "organizations"

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True)
    name: str = Column(String(255), nullable=False)
    slug: str = Column(String(100), unique=True, nullable=False, index=True)
    logo_url: Optional[str] = Column(String(500))
    plan: str = Column(String(50), default="starter", nullable=False)
    stripe_customer_id: Optional[str] = Column(String(255))
    stripe_subscription_id: Optional[str] = Column(String(255))
    subscription_status: Optional[str] = Column(String(50))
    trial_ends_at: Optional[datetime] = Column(DateTime(timezone=True))
    settings: Dict[str, Any] = Column(JSONB, default=dict)
    created_at: datetime = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Optional[datetime] = Column(DateTime(timezone=True), onupdate=datetime.utcnow)

    # Relationships
    settings_relationship = relationship(
        "KeyValueSettings",
        back_populates="organization"
    )
    members = relationship("OrganizationMember", back_populates="organization")
    agents = relationship("Agent", back_populates="organization")
    knowledge_bases = relationship("KnowledgeBase", back_populates="organization")
    documents = relationship("Document", back_populates="organization")
    conversations = relationship("Conversation", back_populates="organization")
    leads = relationship("Lead", back_populates="organization")
    api_keys = relationship("APIKey", back_populates="organization")
    usage_events = relationship("UsageEvent", back_populates="organization")
    audit_logs = relationship("AuditLogModel", back_populates="organization")