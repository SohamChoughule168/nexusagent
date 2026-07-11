from datetime import datetime
from typing import Optional

from sqlalchemy import Column, UUID, DateTime, Text, String
from sqlalchemy.dialects.postgresql import JSONB as PGJSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import func

Base = declarative_base()


class TimestampedModel(Base):
    """Abstract base providing UUID primary key and timestamps."""

    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
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

    organization_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    meta = Column("metadata", PGJSONB, default=dict)
