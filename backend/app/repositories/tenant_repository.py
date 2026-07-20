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
    Tool,
    Memory,
    Notification,
    WebhookSubscription,
    WebhookDelivery,
    BackgroundTask,
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

    def find(
        self,
        kb_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        tag: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Document]:
        """List documents with optional filters (Milestone B, Step 2).

        ``kb_id`` scopes to a knowledge base, ``status`` to a lifecycle state,
        ``tag`` to a metadata tag (ARRAY containment), and ``search`` does a
        case-insensitive substring match on title / filename. Results are
        paginated via ``limit`` / ``offset``.
        """
        stmt = select(Document)
        if kb_id is not None:
            stmt = stmt.where(Document.knowledge_base_id == kb_id)
        if status is not None:
            stmt = stmt.where(Document.status == status)
        if tag is not None:
            stmt = stmt.where(Document.tags.any(tag))
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                (Document.title.ilike(like)) | (Document.filename.ilike(like))
            )
        stmt = self._apply_tenant_filter(stmt)
        stmt = stmt.limit(limit).offset(offset).order_by(Document.created_at.desc())
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


class ToolRepository(TenantAwareRepository[Tool]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, Tool)

    def get_by_name(self, name: str) -> Optional[Tool]:
        """Find a tool by its unique (per-tenant) name."""
        stmt = select(Tool).where(Tool.name == name)
        stmt = self._apply_tenant_filter(stmt)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_type(self, tool_type: str) -> List[Tool]:
        """List tools of a specific type within the tenant."""
        stmt = select(Tool).where(Tool.tool_type == tool_type)
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())

    def get_active(self) -> List[Tool]:
        """List only the enabled tools within the tenant (discovery helper)."""
        stmt = select(Tool).where(Tool.is_active.is_(True))
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())

    def find(
        self,
        tool_type: str = None,
        is_active: bool = None,
        search: str = None,
        allowed_role: str = None,
    ) -> List[Tool]:
        """Discover tools within the tenant using optional filters.

        ``tool_type`` narrows by type, ``is_active`` by enabled state,
        ``search`` does a case-insensitive substring match across name /
        display_name / description, and ``allowed_role`` restricts to tools
        whose ``allowed_roles`` allow-list includes the role (or that have no
        allow-list, i.e. open to all members).
        """
        stmt = select(Tool)
        if tool_type is not None:
            stmt = stmt.where(Tool.tool_type == tool_type)
        if is_active is not None:
            stmt = stmt.where(Tool.is_active.is_(is_active))
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                (Tool.name.ilike(like))
                | (Tool.display_name.ilike(like))
                | (Tool.description.ilike(like))
            )
        if allowed_role is not None:
            # Open tools (empty allow-list) OR explicitly list the role.
            stmt = stmt.where(
                Tool.allowed_roles.is_(None)
                | (Tool.allowed_roles == "{}")
                | (Tool.allowed_roles.any(allowed_role))
            )
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())


class MemoryRepository(TenantAwareRepository[Memory]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, Memory)

    def get_by_key(self, key: str) -> Optional[Memory]:
        """Fetch a memory by its stable per-tenant key (None if absent)."""
        stmt = select(Memory).where(Memory.key == key)
        stmt = self._apply_tenant_filter(stmt)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_category(self, category: str) -> List[Memory]:
        """List all memories in the tenant with the given category."""
        stmt = select(Memory).where(Memory.category == category)
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())

    def search_content(self, query: str) -> List[Memory]:
        """Keyword (non-semantic) substring search over memory content.

        Case-insensitive. Semantic/vector retrieval is deferred to Phase 2.3.
        """
        like = f"%{query}%"
        stmt = select(Memory).where(Memory.content.ilike(like))
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())

    def list_memories(
        self,
        category: Optional[str] = None,
        key: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Memory]:
        """List memories for the tenant with optional category/key filters."""
        stmt = select(Memory)
        if category is not None:
            stmt = stmt.where(Memory.category == category)
        if key is not None:
            stmt = stmt.where(Memory.key == key)
        stmt = self._apply_tenant_filter(stmt)
        stmt = (
            stmt.limit(limit)
            .offset(offset)
            .order_by(Memory.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())


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

    def tools(self) -> ToolRepository:
        return ToolRepository(self.db, self.organization_id)

    def memories(self) -> MemoryRepository:
        return MemoryRepository(self.db, self.organization_id)

    def notifications(self) -> "NotificationRepository":
        return NotificationRepository(self.db, self.organization_id)

    def webhook_subscriptions(self) -> "WebhookSubscriptionRepository":
        return WebhookSubscriptionRepository(self.db, self.organization_id)

    def webhook_deliveries(self) -> "WebhookDeliveryRepository":
        return WebhookDeliveryRepository(self.db, self.organization_id)

    def background_tasks(self) -> "BackgroundTaskRepository":
        return BackgroundTaskRepository(self.db, self.organization_id)


class NotificationRepository(TenantAwareRepository[Notification]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, Notification)

    def get_unread(self, user_id: Optional[uuid.UUID] = None) -> List[Notification]:
        stmt = select(Notification).where(Notification.read.is_(False))
        if user_id is not None:
            stmt = stmt.where(Notification.user_id == user_id)
        stmt = self._apply_tenant_filter(stmt)
        stmt = stmt.order_by(Notification.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())


class WebhookSubscriptionRepository(TenantAwareRepository[WebhookSubscription]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, WebhookSubscription)

    def get_active_for_event(self, event_type: str) -> List[WebhookSubscription]:
        stmt = select(WebhookSubscription).where(
            WebhookSubscription.event_type == event_type,
            WebhookSubscription.is_active.is_(True),
        )
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())


class WebhookDeliveryRepository(TenantAwareRepository[WebhookDelivery]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, WebhookDelivery)


class BackgroundTaskRepository(TenantAwareRepository[BackgroundTask]):
    def __init__(self, db: Session, organization_id: uuid.UUID):
        super().__init__(db, organization_id, BackgroundTask)

    def get_by_type(self, task_type: str) -> List[BackgroundTask]:
        stmt = select(BackgroundTask).where(BackgroundTask.task_type == task_type)
        stmt = self._apply_tenant_filter(stmt)
        return list(self.db.execute(stmt).scalars().all())