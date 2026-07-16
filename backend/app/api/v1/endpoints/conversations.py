import json
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
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.conversation_memory import ConversationMemoryService
from app.services.tenant_context import TenantContext
from app.schemas.orchestrator import OrchestrateRequest

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

    # Conversation Memory (Milestone 5, Phase 1 + 2.1): inject the
    # conversation's *summary* (if any) first, then the token-budgeted recent
    # history, into the LLM prompt. Retrieval above intentionally uses the raw
    # query; only the *generation* prompt is enriched with summary + history,
    # and the RAG context is layered on by ``app.services.rag`` downstream.
    memory = ConversationMemoryService(db, tenant.organization_id)
    enhanced_query, _, _ = memory.build_context(
        conversation_id, payload.message
    )

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
                selected = auto_select_tools(enhanced_query, tools)
                fc = await run_function_calling(
                    enhanced_query,
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
            async for delta in stream_answer(enhanced_query, scored, model):
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

                # Milestone5, Phase2.1: when the conversation crosses a
                # summarization threshold, auto-generate (and persist) a compact
                # summary. Safe no-op offline / below threshold, so normal turns
                # are unaffected and failures never break the chat response.
                try:
                    summ = ConversationMemoryService(s, tenant.organization_id)
                    await summ.maybe_generate_summary(conversation_id)
                except Exception as exc:  # never break the turn on summary errors
                    logger.warning(
                        "auto_summary_failed",
                        conversation_id=str(conversation_id),
                        error=str(exc),
                    )

    return StreamingResponse(event_stream(), media_type="text/plain")


@router.post("/{conversation_id}/orchestrate")
async def orchestrate(
    conversation_id: uuid.UUID,
    payload: OrchestrateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Run a multi-agent orchestrated task for a conversation (Milestone 4, Phase 4).

    Plans (or reuses) a task decomposition across the tenant's agents, executes
    the steps with sequential/parallel scheduling + per-step failure recovery,
    and streams progress as newline-delimited JSON events. Each step output and
    the final synthesised answer are persisted as assistant messages in the
    conversation, so the orchestration trace lives alongside normal chat turns.

    The orchestrator reuses the existing function-calling / tool-execution /
    RAG pipeline per agent step and enforces tenant isolation at every boundary:
    agents are resolved within ``organization_id`` and cross-tenant steps fail to
    resolve (and are recovered, never executed).
    """
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    conversation = repo_factory.conversations().get(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    agent = repo_factory.agents().get(uuid.UUID(str(conversation.agent_id)))

    # Persist the user's goal as a user message (tenant-scoped session).
    user_msg = Message(
        conversation_id=str(conversation_id),
        organization_id=str(tenant.organization_id),
        role="user",
        content=payload.goal,
        token_count=len(payload.goal.split()),
    )
    user_msg.id = uuid.uuid4()
    repo_factory.messages().create(user_msg)

    orchestrator = AgentOrchestrator(tenant.organization_id, db)
    result = await orchestrator.orchestrate(
        payload.goal,
        primary_agent=agent,
        conversation_id=conversation_id,
        halt_on_failure=payload.halt_on_failure,
        max_retries=payload.max_retries,
    )

    # Persist each step output + the final answer as assistant messages, and
    # surface NDJSON progress events to the client.
    async def event_stream():
        parts: List[str] = []

        yield _ndjson(
            "plan",
            {
                "goal": result.goal,
                "status": result.status,
                "steps": [vars(s) for s in result.plan.steps],
            },
        )

        for step in result.step_results:
            # Persist the step result as an assistant message in a fresh session
            # so it survives regardless of the request session lifecycle.
            with db_session_ctx() as s:
                rf = RepositoryFactory(s, tenant.organization_id)
                content = step.output or (step.error or "")
                step_msg = Message(
                    conversation_id=str(conversation_id),
                    organization_id=str(tenant.organization_id),
                    role="assistant",
                    content=content,
                    tool_calls={"calls": step.tool_calls} if step.tool_calls else {},
                    tool_results={"results": step.tool_results} if step.tool_results else {},
                )
                step_msg.meta = {
                    "orchestration": "step",
                    "step_id": step.step_id,
                    "agent_ref": step.agent_ref,
                    "agent_id": step.agent_id,
                    "status": step.status,
                    "attempts": step.attempts,
                }
                step_msg.id = uuid.uuid4()
                rf.messages().create(step_msg)

                conv = rf.conversations().get(conversation_id)
                if conv is not None:
                    conv.message_count = (conv.message_count or 0) + 1
                    rf.conversations().update(conv)

            yield _ndjson(
                "step_result",
                {
                    "step_id": step.step_id,
                    "agent_ref": step.agent_ref,
                    "status": step.status,
                    "attempts": step.attempts,
                    "output": step.output,
                    "error": step.error,
                    "error_type": step.error_type,
                },
            )

        # Stream the final synthesised answer token-by-token.
        final = result.final_answer or ""
        for chunk in _chunk_text(final):
            parts.append(chunk)
            yield _ndjson("token", {"content": chunk})

        # Persist the final answer message.
        with db_session_ctx() as s:
            rf = RepositoryFactory(s, tenant.organization_id)
            final_msg = Message(
                conversation_id=str(conversation_id),
                organization_id=str(tenant.organization_id),
                role="assistant",
                content=final,
            )
            final_msg.meta = {"orchestration": "final", "status": result.status}
            final_msg.id = uuid.uuid4()
            rf.messages().create(final_msg)

            conv = rf.conversations().get(conversation_id)
            if conv is not None:
                conv.message_count = (conv.message_count or 0) + 1
                rf.conversations().update(conv)

        yield _ndjson(
            "done",
            {
                "status": result.status,
                "final_answer": final,
                "step_results": [_step_result_dict(s) for s in result.step_results],
            },
        )

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


def _ndjson(event_type: str, data: Dict[str, Any]) -> str:
    """Serialize one orchestration progress event as an NDJSON line."""
    return json.dumps({"type": event_type, "data": data}) + "\n"


def _chunk_text(text: str, size: int = 24) -> List[str]:
    """Split text into small chunks for token-style streaming."""
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def _step_result_dict(step: Any) -> Dict[str, Any]:
    """Return a JSON-serialisable view of a :class:`PlanStepResult`."""
    return {
        "step_id": step.step_id,
        "agent_ref": step.agent_ref,
        "agent_id": step.agent_id,
        "status": step.status,
        "output": step.output,
        "error": step.error,
        "error_type": step.error_type,
        "attempts": step.attempts,
        "tool_calls": step.tool_calls,
        "tool_results": step.tool_results,
        "depends_on": step.depends_on,
        "duration_ms": step.duration_ms,
    }
