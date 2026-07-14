import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.all_models import Conversation, Message
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _uuid_or_400(value: str, field: str) -> uuid.UUID:
    """Parse a UUID supplied in a request body, returning 400 on failure."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field}: expected a valid UUID",
        )


@router.post(
    "/",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    conversation_data: ConversationCreate,
    organization_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Create a new conversation."""
    # NOTE: Tenant scoping is enforced in later milestones. organization_id is
    # supplied here as a stand-in for the authenticated principal until the
    # auth/RBAC dependency is wired in.
    # TODO: Add auth dependency to derive organization_id from the authenticated principal.
    repo_factory = RepositoryFactory(db, organization_id)
    conversations_repo = repo_factory.conversations()

    agent_id = _uuid_or_400(conversation_data.agent_id, "agent_id")
    agent = repo_factory.agents().get(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    conversation = Conversation(
        organization_id=organization_id,
        agent_id=agent_id,
        session_id=conversation_data.session_id,
        user_identifier=conversation_data.user_identifier,
        user_metadata=conversation_data.user_metadata or {},
        status=conversation_data.status or "active",
    )
    # The live schema's id columns carry no DB-side default, so the primary
    # key is assigned explicitly (matching the existing test fixtures). This is
    # the conversation/message PK, never the tenant (organization_id).
    conversation.id = uuid.uuid4()

    return conversations_repo.create(conversation)


@router.get("/", response_model=List[ConversationResponse])
def list_conversations(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """List conversations for the current context."""
    # NOTE: Tenant scoping is enforced in later milestones.
    # TODO: Add auth dependency to derive organization_id from the authenticated principal.
    repo_factory = RepositoryFactory(db, organization_id)
    conversations_repo = repo_factory.conversations()
    return conversations_repo.get_all()


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_message(
    conversation_id: uuid.UUID,
    message_data: MessageCreate,
    organization_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Add a message to a conversation."""
    # NOTE: Tenant scoping is enforced in later milestones.
    # TODO: Add auth dependency to derive organization_id from the authenticated principal.
    repo_factory = RepositoryFactory(db, organization_id)
    conversations_repo = repo_factory.conversations()
    messages_repo = repo_factory.messages()

    conversation = conversations_repo.get(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    message = Message(
        conversation_id=str(conversation_id),
        organization_id=str(organization_id),
        role=message_data.role,
        content=message_data.content,
        token_count=message_data.token_count or 0,
        citations=message_data.citations or {},
        tool_calls=message_data.tool_calls or {},
        tool_results=message_data.tool_results or {},
        model_provider=message_data.model_provider,
        model_name=message_data.model_name,
        cost_usd=message_data.cost_usd or 0.0,
    )
    # Same explicit-PK handling as Conversation (no DB-side default on id).
    message.id = uuid.uuid4()

    return messages_repo.create(message)


@router.get(
    "/{conversation_id}/messages",
    response_model=List[MessageResponse],
)
def list_messages(
    conversation_id: uuid.UUID,
    organization_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """List messages for a conversation."""
    # NOTE: Tenant scoping is enforced in later milestones.
    # TODO: Add auth dependency to derive organization_id from the authenticated principal.
    repo_factory = RepositoryFactory(db, organization_id)
    conversations_repo = repo_factory.conversations()
    messages_repo = repo_factory.messages()

    conversation = conversations_repo.get(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return messages_repo.get_by_conversation(conversation_id)
