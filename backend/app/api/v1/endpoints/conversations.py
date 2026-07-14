import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context
from app.core.config import settings
from app.core.logging import get_logger
from app.core.database import get_db, db_session as db_session_ctx
from app.models.all_models import Conversation, Message
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.conversation import (
    ChatMessageRequest,
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
)
from app.services.function_calling import (
    auto_select_tools,
    discover_tools,
    function_calling_enabled,
    run_function_calling,
    stream_final_answer,
)
from app.services.rag import (
    build_sources,
    compose_answer_offline,
    rag_llm_enabled,
    retrieve_chunks_for_query,
    stream_answer,
)
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/conversations", tags=["conversations"])

logger = get_logger(__name__)


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
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Create a new conversation for the authenticated principal's tenant."""
    # Tenant isolation is enforced by deriving organization_id from the
    # authenticated principal (see app.core.auth_dependencies), never from
    # request data.
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    conversations_repo = repo_factory.conversations()

    agent_id = _uuid_or_400(conversation_data.agent_id, "agent_id")
    agent = repo_factory.agents().get(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    conversation = Conversation(
        organization_id=tenant.organization_id,
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
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List conversations for the authenticated principal's tenant."""
    repo_factory = RepositoryFactory(db, tenant.organization_id)
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
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Add a message to a conversation in the authenticated principal's tenant."""
    repo_factory = RepositoryFactory(db, tenant.organization_id)
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
        organization_id=str(tenant.organization_id),
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
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List messages for a conversation in the authenticated principal's tenant."""
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    conversations_repo = repo_factory.conversations()
    messages_repo = repo_factory.messages()

    conversation = conversations_repo.get(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return messages_repo.get_by_conversation(conversation_id)


@router.post("/{conversation_id}/chat")
async def chat(
    conversation_id: uuid.UUID,
    payload: ChatMessageRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Conversational RAG chat turn for a conversation.

    Persists the user's message, retrieves the most relevant embedded chunks
    from the organization's knowledge bases (optionally scoped via
    ``knowledge_base_ids``), then streams a grounded answer (locally offline, or
    via the configured LLM when ``RAG_LLM_PROVIDER`` + a key are set). The
    assistant reply and its source citations are persisted after the stream.

    Tenant isolation: the conversation, its agent, and the searched knowledge
    bases are all resolved within the authenticated principal's organization.
    """
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    conversation = repo_factory.conversations().get(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    agent = repo_factory.agents().get(uuid.UUID(str(conversation.agent_id)))
    model = agent.model_name if agent else settings.RAG_LLM_MODEL

    # Persist the user's message up front (tenant-scoped session).
    user_msg = Message(
        conversation_id=str(conversation_id),
        organization_id=str(tenant.organization_id),
        role="user",
        content=payload.message,
        token_count=len(payload.message.split()),
    )
    user_msg.id = uuid.uuid4()
    repo_factory.messages().create(user_msg)

    # Retrieve relevant chunks across the organization's knowledge bases.
    kb_ids = (
        [uuid.UUID(str(k)) for k in payload.knowledge_base_ids]
        if payload.knowledge_base_ids
        else None
    )
    scored = retrieve_chunks_for_query(
        tenant.organization_id, db, payload.message, payload.top_k, kb_ids
    )
    citations = build_sources(scored)
    agent_system_prompt = agent.system_prompt if agent else None
    model_provider = agent.model_provider if agent else "openrouter"

    async def event_stream():
        parts: List[str] = []
        # Persisted on the assistant message: the executed tool calls / results.
        tool_calls_payload: Dict[str, Any] = {}
        tool_results_payload: Dict[str, Any] = {}

        # Function Calling integration: when an LLM is configured and the tenant
        # has active tools, ask the LLM to auto-select + call tools, execute them
        # inside the tenant, inject the results, then stream the final grounded
        # answer. Falls back to the standard RAG answer on any failure so the
        # user always receives a response.
        if function_calling_enabled(tenant.organization_id, db, agent):
            try:
                tools = discover_tools(tenant.organization_id, db, agent)
                selected = auto_select_tools(payload.message, tools)
                fc = await run_function_calling(
                    payload.message,
                    tenant.organization_id,
                    db,
                    model,
                    selected,
                    scored,
                    agent_system_prompt=agent_system_prompt,
                )
                async for delta in stream_final_answer(fc.messages, model):
                    parts.append(delta)
                    yield delta
                tool_calls_payload = {"calls": fc.tool_calls, "model": model}
                tool_results_payload = {"results": fc.tool_results}
            except Exception as exc:  # resilience: never let FC break the turn
                logger.warning(
                    "function_calling_failed_fallback_to_rag",
                    conversation_id=str(conversation_id),
                    error=str(exc),
                )
                text = compose_answer_offline(scored)
                parts.append(text)
                yield text
        elif rag_llm_enabled() and scored:
            async for delta in stream_answer(payload.message, scored, model):
                parts.append(delta)
                yield delta
        else:
            text = compose_answer_offline(scored)
            parts.append(text)
            yield text

        # Persist the assistant reply + citations in a fresh session so it
        # survives regardless of the request session lifecycle.
        full = "".join(parts)
        with db_session_ctx() as s:
            rf = RepositoryFactory(s, tenant.organization_id)
            assistant = Message(
                conversation_id=str(conversation_id),
                organization_id=str(tenant.organization_id),
                role="assistant",
                content=full,
                citations={"sources": citations},
                tool_calls=tool_calls_payload,
                tool_results=tool_results_payload,
                model_provider=model_provider,
                model_name=model,
                token_count=len(full.split()),
            )
            assistant.id = uuid.uuid4()
            rf.messages().create(assistant)

            conv = rf.conversations().get(conversation_id)
            if conv is not None:
                conv.message_count = (conv.message_count or 0) + 2
                rf.conversations().update(conv)

    return StreamingResponse(event_stream(), media_type="text/plain")
