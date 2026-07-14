"""Routing API endpoint (Milestone 4, Phase 5).

Exposes ``POST /conversations/{conversation_id}/route``, which integrates the
Multi-Agent Router into the existing orchestration pipeline. The flow reuses
the Conversations API, TenantContext and RepositoryFactory exactly as the chat
and orchestrate endpoints do: the conversation and its agent are resolved within
the authenticated tenant, the user's query is persisted, then the router selects
and dispatches agent(s) and the result (per-agent outputs + final answer) is
persisted as assistant messages and streamed as NDJSON events.

Tenant isolation: identical to the rest of the pipeline -- ``organization_id``
is derived solely from the authenticated principal, and the router resolves
agents/tools strictly within that organization.
"""
import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context
from app.core.database import get_db, db_session as db_session_ctx
from app.models.all_models import Conversation, Message
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.routing import RouteRequest
from app.services.multi_agent_router import MultiAgentRouter
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/conversations", tags=["routing"])


@router.post("/{conversation_id}/route")
async def route(
    conversation_id: str,
    payload: RouteRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Route a query across the tenant's agents and dispatch to the best one(s).

    Selects agent(s) via the named routing policy, dispatches them through the
    function-calling pipeline (or the Agent Orchestrator in ``orchestrate`` mode),
    and streams progress as newline-delimited JSON: ``decision`` -> one
    ``dispatch_result`` per dispatched agent -> ``token`` chunks of the final
    answer -> ``done``. Each agent output and the final answer are persisted as
    assistant messages on the conversation so the routing trace lives alongside
    normal chat turns.
    """
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    conversation = repo_factory.conversations().get(_as_uuid(conversation_id))
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    primary_agent = repo_factory.agents().get(_as_uuid(str(conversation.agent_id)))

    # Persist the user's query as a user message (tenant-scoped session).
    user_msg = Message(
        conversation_id=str(conversation_id),
        organization_id=str(tenant.organization_id),
        role="user",
        content=payload.query,
        token_count=len(payload.query.split()),
    )
    user_msg.id = _uuid()
    repo_factory.messages().create(user_msg)

    router_service = MultiAgentRouter(tenant.organization_id, db)
    result = await router_service.route(
        payload.query,
        conversation_id=conversation_id,
        primary_agent=primary_agent,
        policy=payload.policy,
        top_k=payload.top_k,
        mode=payload.mode,
        halt_on_failure=payload.halt_on_failure,
        max_retries=payload.max_retries,
    )

    async def event_stream():
        yield _ndjson("decision", result.decision.to_dict())

        for out in result.outputs:
            # Persist each dispatched agent's output as an assistant message in a
            # fresh session so it survives the request session lifecycle.
            with db_session_ctx() as s:
                rf = RepositoryFactory(s, tenant.organization_id)
                content = out.output or (out.error or "")
                out_msg = Message(
                    conversation_id=str(conversation_id),
                    organization_id=str(tenant.organization_id),
                    role="assistant",
                    content=content,
                    tool_calls={"calls": out.tool_calls} if out.tool_calls else {},
                    tool_results={"results": out.tool_results} if out.tool_results else {},
                )
                out_msg.meta = {
                    "routing": "agent_output",
                    "agent_ref": out.agent_ref,
                    "agent_id": out.agent_id,
                    "status": out.status,
                }
                out_msg.id = _uuid()
                rf.messages().create(out_msg)

                conv = rf.conversations().get(_as_uuid(conversation_id))
                if conv is not None:
                    conv.message_count = (conv.message_count or 0) + 1
                    rf.conversations().update(conv)

            yield _ndjson(
                "dispatch_result",
                {
                    "agent_ref": out.agent_ref,
                    "agent_id": out.agent_id,
                    "name": out.name,
                    "status": out.status,
                    "output": out.output,
                    "error": out.error,
                },
            )

        # Stream the final answer token-by-token.
        final = result.answer or ""
        for chunk in _chunk_text(final):
            yield _ndjson("token", {"content": chunk})

        # Persist the final synthesized answer message.
        with db_session_ctx() as s:
            rf = RepositoryFactory(s, tenant.organization_id)
            final_msg = Message(
                conversation_id=str(conversation_id),
                organization_id=str(tenant.organization_id),
                role="assistant",
                content=final,
            )
            final_msg.meta = {
                "routing": "final",
                "mode": result.mode,
                "status": result.status,
            }
            final_msg.id = _uuid()
            rf.messages().create(final_msg)

            conv = rf.conversations().get(_as_uuid(conversation_id))
            if conv is not None:
                conv.message_count = (conv.message_count or 0) + 1
                rf.conversations().update(conv)

        yield _ndjson(
            "done",
            {
                "status": result.status,
                "mode": result.mode,
                "final_answer": final,
                "outputs": [o.to_dict() for o in result.outputs],
                "policy_name": result.decision.policy_name,
            },
        )

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_uuid(value: str):
    import uuid

    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _uuid():
    import uuid

    return uuid.uuid4()


def _ndjson(event_type: str, data: Dict[str, Any]) -> str:
    """Serialize one routing progress event as an NDJSON line."""
    return json.dumps({"type": event_type, "data": data}) + "\n"


def _chunk_text(text: str, size: int = 24) -> list:
    """Split text into small chunks for token-style streaming."""
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]
