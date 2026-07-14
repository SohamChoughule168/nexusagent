from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import Column, UUID, DateTime, Text, String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB as PGJSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import func
from sqlalchemy.orm import relationship

Base = declarative_base()


class TimestampedModel(Base):
    """Abstract base providing UUID primary key and timestamps."""

    __abstract__ = True

    # Python-side default guarantees a PK is always populated even when the
    # underlying migration omitted a DB-level server_default (the live schema
    # was created before server_defaults were added), while the server_default
    # keeps raw SQL inserts consistent. Explicit ids supplied in code win.
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )


class MultiTenantModel(TimestampedModel):
    """
    Abstract marker base for tenant-scoped entities.

    Subclasses MUST declare their own ``organization_id`` column so each
    concrete table owns the tenant key explicitly.
    """

    __abstract__ = True


class AuditLogModel(MultiTenantModel):
    """Immutable audit trail entry. Tenant-scoped via organization_id."""

    __tablename__ = "audit_logs"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    meta = Column("metadata", PGJSONB, default=dict)

    user = relationship("User", back_populates="audit_logs")
    organization = relationship("Organization", back_populates="audit_logs")
