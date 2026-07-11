import uuid
from typing import TypeVar, Generic, Type, Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from contextlib import contextmanager

from app.models.all_models import Base
from app.models.user import User
from app.models.organization import Organization
from app.models.all_models import (
    Agent,
    KnowledgeBase,
    Document,
    DocumentChunk,
    Conversation,
    Message,
    Lead,
    UsageEvent,
    APIKey,
    OrganizationMember,
    ToolConfig,
)

T = TypeVar('T', bound=Base)


class TenantAwareRepository(Generic[T]):
    """
    Base repository that enforces tenant isolation at the database level.
    All queries are automatically filtered by organization_id.
    """

    def __init__(self, db: Session, organization_id: uuid.UUID, model_class: Type[T]):
        self.db = db
        self.organization_id = organization_id
        self.model_class = model_class

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        try:
            yield self.db
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

    def _apply_tenant_filter(self, query):
        """Apply tenant isolation filter to query."""
        if hasattr(self.model_class, 'organization_id'):
            return query.filter(self.model_class.organization_id == self.organization_id)
        return query

    def get(self, id: uuid.UUID) -> Optional[T]:
        """Get a single record by ID, ensuring tenant isolation."""
        stmt = select(self.model_class).where(
            self.model_class.id == id
        )
        stmt = self._apply_tenant_filter(stmt)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """Get all records for the organization."""
        stmt = select(self.model_class)
        stmt = self._apply_tenant_filter(stmt)
        stmt = stmt.limit(limit).offset(offset).order_by(self.model_class.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def create(self, obj: T) -> T:
        """Create a new record."""
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, obj: T) -> T:
        """Update an existing record."""
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj: T) -> None:
        """Delete a record (soft delete if supported)."""
        self.db.delete(obj)
        self.db.commit()

    def count(self) -> int:
        """Count records for the organization."""
        from sqlalchemy import func
        stmt = select(func.count(self.model_class.id))
        stmt = self._apply_tenant_filter(stmt)
        return self.db.execute(stmt).scalar() or 0


# Specialized repositories with additional methods

class UserRepository(TenantAwareRepository[User]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, User)

    def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email)
        stmt = self._apply_tenant_filter(stmt)
        return self.db.execute(stmt).scalar_one_or_none()


class OrganizationRepository(TenantAwareRepository[Organization]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, Organization)

    def get_by_slug(self, slug: str) -> Optional[Organization]:
        stmt = select(Organization).where(Organization.slug == slug)
        stmt = self._apply_tenant_filter(stmt)
        return self.db.execute(stmt).scalar_one_or_none()


class OrganizationMemberRepository(TenantAwareRepository[OrganizationMember]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, OrganizationMember)

    def get_by_user(self, user_id: uuid.UUID) -> Optional[OrganizationMember]:
        stmt = select(OrganizationMember).where(OrganizationMember.user_id == user_id)
        stmt = self._apply_tenant_filter(stmt)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_members_with_users(self) -> List[Dict[str, Any]]:
        """Get all members with their user details."""
        stmt = select(OrganizationMember, User).join(
            User, OrganizationMember.user_id == User.id
        ).where(OrganizationMember.organization_id == self.organization_id)
        results = self.db.execute(stmt).all()
        return [
            {
                "member": member,
                "user": user
            }
            for member, user in results
        ]


class AgentRepository(TenantAwareRepository[Agent]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, Agent)

    def get_by_public_id(self, public_id: str) -> Optional[Agent]:
        stmt = select(Agent).where(Agent.public_id == public_id)
        stmt = self._apply_tenant_filter(stmt)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_active_agents(self) -> List[Agent]:
        stmt = select(Agent).where(Agent.status == "active")
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())


class KnowledgeBaseRepository(TenantAwareRepository[KnowledgeBase]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, KnowledgeBase)

    def get_default(self) -> Optional[KnowledgeBase]:
        stmt = select(KnowledgeBase).where(KnowledgeBase.default == True)
        stmt = self._apply_tenant_filter(stmt)
        return self.db.execute(stmt).scalar_one_or_none()


class DocumentRepository(TenantAwareRepository[Document]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, Document)

    def get_by_knowledge_base(self, kb_id: uuid.UUID) -> List[Document]:
        stmt = select(Document).where(Document.knowledge_base_id == kb_id)
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_status(self, status: str) -> List[Document]:
        stmt = select(Document).where(Document.status == status)
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())


class DocumentChunkRepository(TenantAwareRepository[DocumentChunk]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, DocumentChunk)

    def get_by_document(self, document_id: uuid.UUID) -> List[DocumentChunk]:
        stmt = select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_knowledge_base(self, kb_id: uuid.UUID) -> List[DocumentChunk]:
        stmt = select(DocumentChunk).where(DocumentChunk.knowledge_base_id == kb_id)
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())


class ConversationRepository(TenantAwareRepository[Conversation]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, Conversation)

    def get_by_session_id(self, session_id: str) -> Optional[Conversation]:
        stmt = select(Conversation).where(Conversation.session_id == session_id)
        stmt = self._apply_tenant_filter(stmt)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_agent(self, agent_id: uuid.UUID) -> List[Conversation]:
        stmt = select(Conversation).where(Conversation.agent_id == agent_id)
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())


class MessageRepository(TenantAwareRepository[Message]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, Message)

    def get_by_conversation(self, conversation_id: uuid.UUID, limit: int = 50) -> List[Message]:
        stmt = select(Message).where(Message.conversation_id == conversation_id)
        stmt = self._apply_tenant_filter(stmt)
        stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def get_recent_messages(self, conversation_id: uuid.UUID, limit: int = 20) -> List[Message]:
        stmt = select(Message).where(Message.conversation_id == conversation_id)
        stmt = self._apply_tenant_filter(stmt)
        stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())


class LeadRepository(TenantAwareRepository[Lead]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, Lead)

    def get_by_status(self, status: str) -> List[Lead]:
        stmt = select(Lead).where(Lead.status == status)
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_agent(self, agent_id: uuid.UUID) -> List[Lead]:
        stmt = select(Lead).where(Lead.agent_id == agent_id)
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())


class UsageEventRepository(TenantAwareRepository[UsageEvent]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, UsageEvent)

    def get_by_type(self, event_type: str) -> List[UsageEvent]:
        stmt = select(UsageEvent).where(UsageEvent.event_type == event_type)
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())


class ToolConfigRepository(TenantAwareRepository[ToolConfig]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, ToolConfig)

    def get_by_tool_name(self, tool_name: str) -> Optional[ToolConfig]:
        stmt = select(ToolConfig).where(ToolConfig.tool_name == tool_name)
        stmt = self._apply_tenant_filter(stmt)
        return self.db.execute(stmt).scalar_one_or_none()


# Factory for creating repositories
class RepositoryFactory:
    """Factory for creating tenant-aware repositories."""

    def __init__(self, db: Session, organization_id: uuid.UUID):
        self.db = db
        self.organization_id = organization_id

    def users(self) -> UserRepository:
        return UserRepository(self.db, self.organization_id)

    def organizations(self) -> OrganizationRepository:
        return OrganizationRepository(self.db, self.organization_id)

    def organization_members(self) -> OrganizationMemberRepository:
        return OrganizationMemberRepository(self.db, self.organization_id)

    def agents(self) -> AgentRepository:
        return AgentRepository(self.db, self.organization_id)

    def knowledge_bases(self) -> KnowledgeBaseRepository:
        return KnowledgeBaseRepository(self.db, self.organization_id)

    def documents(self) -> DocumentRepository:
        return DocumentRepository(self.db, self.organization_id)

    def document_chunks(self) -> DocumentChunkRepository:
        return DocumentChunkRepository(self.db, self.organization_id)

    def conversations(self) -> ConversationRepository:
        return ConversationRepository(self.db, self.organization_id)

    def messages(self) -> MessageRepository:
        return MessageRepository(self.db, self.organization_id)

    def leads(self) -> LeadRepository:
        return LeadRepository(self.db, self.organization_id)

    def usage_events(self) -> UsageEventRepository:
        return UsageEventRepository(self.db, self.organization_id)

    def tool_configs(self) -> ToolConfigRepository:
        return ToolConfigRepository(self.db, self.organization_id)