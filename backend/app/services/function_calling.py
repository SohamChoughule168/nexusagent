"""Function Calling service (Milestone 4, Phase 3).

Integrates LLM tool / function calling into the existing Conversation + RAG
pipeline. The service is deliberately a *thin orchestration layer* that reuses
(rather than duplicates) the components delivered in earlier milestones:

* **Tool Registry** (``app.services.tool_registry``) -- the supported tool
  types and ``input_schema`` shape produced by Phase 1.
* **Tool Execution Engine** (``app.services.tool_executor``) --
  ``ToolExecutionEngine``, ``ToolResult`` and ``validate_arguments`` (used for
  runtime Tool Argument Validation). Every tool runs through the engine, so
  execution safety / isolation / tenant-scoping are inherited unchanged.
* **ToolRepository** (via ``RepositoryFactory``) -- tenant-scoped tool
  discovery (``get_active``) and resolution by name (``get_by_name``), which
  enforces tenant isolation at the SQL ``WHERE`` level.
* **Conversation API + Streaming Chat** (``app.ai.providers``) -- the existing
  ``OpenRouterProvider`` is OpenAI-compatible: it already emits the ``tools`` /
  ``tool_choice`` payload and parses ``tool_calls``. We reuse it directly so the
  wire format matches the OpenAI tool-calling contract exactly.
* **RAG Pipeline** (``app.services.rag``) -- retrieval
  (``retrieve_chunks_for_query``), source citation building (``build_sources``),
  the offline composer (``compose_answer_offline``) and the ``rag_llm_enabled``
  feature gate.

The flow for a chat turn is:

1. Discover the tenant's (optionally agent-scoped) active tools.
2. Convert each ``Tool`` into an **OpenAI-compatible function schema**
   (Function Schema Generation) and let the LLM **auto-select** which to call
   (``tool_choice="auto"`` -> Automatic Tool Selection).
3. For each selected tool call, **validate the arguments** against the tool's
   ``input_schema``, resolve the tool *inside the tenant*, and **execute** it
   via the engine.
4. **Inject the tool results** back into the message list as ``tool``-role
   messages, then prompt the LLM once more for the final grounded answer
   (streamed to the client and persisted on the conversation).

Tenant isolation is preserved at every step: tools are discovered and resolved
within ``organization_id`` derived from the authenticated principal, and the
execution engine re-checks tenant ownership before running anything.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.ai.providers.base import (
    BaseLLMProvider,
    GenerationRequest,
    Message,
    MessageRole,
)
from app.ai.providers.openrouter import OpenRouterProvider
from app.core.config import settings
from app.core.logging import get_logger
from app.models.all_models import DocumentChunk, Tool
from app.repositories.tenant_repository import RepositoryFactory
from app.services.rag import (
    build_sources,
    compose_answer_offline,
    rag_llm_enabled,
    retrieve_chunks_for_query,
)
from app.services.tool_executor import ToolExecutionEngine, ToolResult, validate_arguments

logger = get_logger(__name__)

# Cap on retrieved-context characters passed to the LLM (mirrors rag._MAX_CONTEXT_CHARS).
_MAX_CONTEXT_CHARS = 6000

# Shared, stateless execution engine instance (tenant-scoped per call, like the
# API endpoint's instance in app.api.v1.endpoints.tools).
_engine = ToolExecutionEngine()


# ---------------------------------------------------------------------------
# Function schema generation (OpenAI-compatible)
# ---------------------------------------------------------------------------


def generate_function_schema(tool: Tool) -> Dict[str, Any]:
    """Build an OpenAI-compatible function/tool schema from a registered ``Tool``.

    The tool's ``input_schema`` (a JSON-Schema object produced by the Phase 1
    registry) becomes the ``parameters`` block. If a tool has no schema we emit
    an empty ``{"type": "object", "properties": {}}`` so the LLM always receives
    a valid parameter object.

    Returns e.g.::

        {
            "type": "function",
            "function": {
                "name": "weather_lookup",
                "description": "Fetches current weather for a city.",
                "parameters": {"type": "object", "properties": {"city": {...}}},
            },
        }
    """
    schema = tool.input_schema or {}
    if not schema:
        schema = {"type": "object", "properties": {}}
    description = (tool.description or tool.display_name or tool.name or "").strip()
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": description,
            "parameters": schema,
        },
    }


def generate_function_schemas(tools: List[Tool]) -> List[Dict[str, Any]]:
    """Batch form of :func:`generate_function_schema`."""
    return [generate_function_schema(t) for t in tools]


# ---------------------------------------------------------------------------
# Automatic tool selection
# ---------------------------------------------------------------------------


def auto_select_tools(
    query: str,
    tools: List[Tool],
    max_tools: Optional[int] = None,
) -> List[Tool]:
    """Automatic tool selection: choose the candidate tools to offer the LLM.

    The LLM still makes the final call decision (``tool_choice='auto'``); this
    is the deterministic pre-filter that narrows the candidate set to the most
    relevant tools for the current query, reducing prompt size and the chance
    of irrelevant calls.

    Strategy: rank tools by keyword overlap between the query and the tool's
    name + display name + description. If any tools overlap, return the
    overlapping subset (capped at ``max_tools``); if none overlap, return *all*
    tools so the LLM keeps full freedom to choose. An empty/whitespace query
    returns all tools.
    """
    if not tools:
        return []

    q = (query or "").lower()
    if not q.strip():
        return _cap(tools, max_tools)

    tokens = {tok for tok in q.split() if len(tok) > 2}
    if not tokens:
        return _cap(tools, max_tools)

    scored: List[Tuple[int, Tool]] = []
    for tool in tools:
        text = " ".join(
            [tool.name or "", tool.display_name or "", tool.description or ""]
        ).lower()
        overlap = sum(1 for tok in tokens if tok in text)
        scored.append((overlap, tool))

    scored.sort(key=lambda x: x[0], reverse=True)
    matched = [t for overlap, t in scored if overlap > 0]
    if not matched:
        return _cap(tools, max_tools)
    return _cap(matched, max_tools)


def _cap(tools: List[Tool], max_tools: Optional[int]) -> List[Tool]:
    if max_tools is None:
        return list(tools)
    return list(tools)[: max_tools]


# ---------------------------------------------------------------------------
# Tool argument validation (reuses the engine's runtime validator)
# ---------------------------------------------------------------------------


def validate_tool_arguments(tool: Tool, arguments: Any) -> List[str]:
    """Validate runtime ``arguments`` for ``tool`` against its ``input_schema``.

    Thin, named wrapper over the engine's ``validate_arguments`` so Tool
    Argument Validation is a first-class, independently testable concern.
    Returns a list of human-readable errors (empty == valid).
    """
    return validate_arguments(tool.input_schema, arguments)


# ---------------------------------------------------------------------------
# Tool discovery (tenant-scoped) + per-agent scoping
# ---------------------------------------------------------------------------


def discover_tools(
    organization_id: uuid.UUID,
    db,
    agent: Optional[Any] = None,
) -> List[Tool]:
    """Discover the tools available to a conversation turn.

    Tenant isolation is enforced by the tenant-scoped ``ToolRepository``: only
    this organization's tools are ever returned. When the agent carries an
    ``enabled_tool_ids`` allow-list in its ``config``, the candidate set is
    narrowed to exactly those tools (still resolved *within* the tenant, so a
    tool id from another org resolves to nothing and is skipped).

    Falls back to all of the organization's active tools when no allow-list is
    configured -- the LLM then performs the final automatic selection.
    """
    repo = RepositoryFactory(db, organization_id).tools()

    enabled_ids = None
    if agent is not None:
        config = getattr(agent, "config", None) or {}
        enabled_ids = config.get("enabled_tool_ids")

    if enabled_ids:
        tools: List[Tool] = []
        for tid in enabled_ids:
            try:
                tool = repo.get(uuid.UUID(str(tid)))
            except (ValueError, TypeError, AttributeError):
                tool = None
            if tool is not None:
                tools.append(tool)
        return tools

    return repo.get_active()


# ---------------------------------------------------------------------------
# Tool-call parsing + tenant-scoped resolution & execution
# ---------------------------------------------------------------------------


def parse_tool_call(tool_call: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
    """Parse one LLM ``tool_call`` into ``(name, arguments, parse_error)``.

    OpenAI-compatible providers return ``tool_call`` as::

        {"id": "call_abc", "type": "function",
         "function": {"name": "weather_lookup", "arguments": '{"city": "Paris"}'}}

    ``arguments`` is a JSON *string* in the wire format, but some providers pass
    an already-parsed object. We accept both and surface a clear parse error
    (returned as the third tuple element) so the caller can turn it into a
    controlled error result instead of raising.
    """
    fn = tool_call.get("function", {}) or {}
    name = fn.get("name")
    raw = fn.get("arguments")

    if isinstance(raw, dict):
        return name, raw, None
    if isinstance(raw, str):
        if not raw.strip():
            return name, {}, None
        try:
            return name, json.loads(raw), None
        except json.JSONDecodeError as exc:
            return name, {}, f"invalid JSON arguments: {exc}"
    if raw is None:
        return name, {}, None
    # Unexpected type (e.g. a number) -> treat as a parse failure.
    return name, {}, f"arguments must be a JSON object or string, got {type(raw).__name__}"


def execute_tool_call(
    tool_call: Dict[str, Any],
    organization_id: uuid.UUID,
    db,
) -> Tuple[Optional[Tool], ToolResult]:
    """Resolve, validate and execute a single LLM ``tool_call`` within a tenant.

    Returns the executed ``Tool`` (or ``None`` if it could not be resolved) and a
    normalized ``ToolResult``. Never raises: parse failures, unknown tools,
    argument-validation failures and execution failures all become error
    results.

    Tenant isolation: the tool is resolved via the tenant-scoped repository, so
    a tool owned by another organization cannot be addressed -- the call becomes
    a ``not_found`` error result instead of a cross-tenant execution.
    """
    name, args, parse_error = parse_tool_call(tool_call)

    if parse_error:
        logger.warning(
            "function_calling_argument_parse_error",
            tool_name=name,
            error=parse_error,
        )
        return None, _synthetic_error(
            name, args, parse_error, "argument_validation"
        )

    repo = RepositoryFactory(db, organization_id).tools()
    tool = repo.get_by_name(name) if name else None
    if tool is None:
        logger.warning(
            "function_calling_tool_not_found",
            tool_name=name,
            organization_id=str(organization_id),
        )
        return None, ToolResult(
            execution_id=str(uuid.uuid4()),
            success=False,
            tool_id=None,
            tool_name=name or "",
            tool_type="",
            arguments=args,
            error=f"Tool '{name}' not found in this tenant",
            error_type="not_found",
            started_at=datetime.now(timezone.utc),
            meta={"organization_id": str(organization_id)},
        )

    # The engine re-validates arguments against the tool's input_schema and runs
    # the tenant-resolved tool, so execution safety/isolation are inherited.
    return tool, _engine.execute(tool, args)


def _synthetic_error(
    name: Optional[str],
    args: Dict[str, Any],
    error: str,
    error_type: str,
) -> ToolResult:
    return ToolResult(
        execution_id=str(uuid.uuid4()),
        success=False,
        tool_id=None,
        tool_name=name or "",
        tool_type="",
        arguments=args,
        error=error,
        error_type=error_type,
        started_at=datetime.now(timezone.utc),
        meta={},
    )


# ---------------------------------------------------------------------------
# LLM function-calling orchestration + tool result injection
# ---------------------------------------------------------------------------


@dataclass
class FunctionCallingResult:
    """Outcome of one function-calling round for a chat turn.

    ``messages`` is the augmented OpenAI-style message list (system + user
    context + assistant tool_calls + tool results) ready to be sent back to the
    LLM to generate the final grounded answer. ``tool_calls`` and ``tool_results``
    are persisted on the assistant message.
    """

    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    messages: List[Message] = field(default_factory=list)
    called_tools: List[Tool] = field(default_factory=list)


def _provider(api_key: str, base_url: str) -> BaseLLMProvider:
    """Construct the OpenAI-compatible chat provider (injectable for tests)."""
    return OpenRouterProvider(api_key=api_key, base_url=base_url)


def _build_context(scored: List[Tuple[DocumentChunk, float]]) -> str:
    parts = []
    for i, (chunk, _score) in enumerate(scored):
        snippet = (chunk.content or "")[:_MAX_CONTEXT_CHARS]
        parts.append(f"[Source {i + 1}]\n{snippet}")
    return "\n\n".join(parts)


def _system_prompt(agent_system_prompt: Optional[str]) -> str:
    base = (
        "You are a helpful assistant. You have access to tools that can fetch "
        "live data or perform actions. Call a tool when it is needed to answer "
        "the user's question; otherwise answer directly. When you receive tool "
        "results, use them to give a grounded, concise answer and cite the "
        "relevant [Source N] numbers where applicable."
    )
    if agent_system_prompt:
        return f"{agent_system_prompt}\n\n{base}"
    return base


def _user_prompt(query: str, context: str) -> str:
    if context:
        return f"Context:\n{context}\n\nQuestion: {query}"
    return query


async def run_function_calling(
    query: str,
    organization_id: uuid.UUID,
    db,
    model_name: str,
    tools: List[Tool],
    scored: List[Tuple[DocumentChunk, float]],
    agent_system_prompt: Optional[str] = None,
    temperature: float = 0.2,
) -> FunctionCallingResult:
    """Run one function-calling round: ask the LLM to auto-select tools, then
    validate + execute the selected tool calls inside the tenant.

    Returns the augmented message list (with tool results injected) plus the
    executed tool calls / results, ready for the final answer generation.
    """
    schemas = generate_function_schemas(tools)
    system = _system_prompt(agent_system_prompt)
    context = _build_context(scored)
    messages = [
        Message(role=MessageRole.SYSTEM, content=system),
        Message(role=MessageRole.USER, content=_user_prompt(query, context)),
    ]

    provider = _provider(
        settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY or "",
        settings.OPENROUTER_BASE_URL,
    )
    try:
        response = await provider.generate(
            GenerationRequest(
                messages=messages,
                model=model_name,
                temperature=temperature,
                max_tokens=1024,
                tools=schemas,
                tool_choice="auto",
            )
        )
    finally:
        await provider.close()

    tool_calls = response.tool_calls or []
    if not tool_calls:
        # The LLM chose not to call any tool; the direct content (if present) is
        # the answer. No tool results to inject.
        return FunctionCallingResult(
            tool_calls=[],
            tool_results=[],
            messages=messages,
            called_tools=[],
        )

    # Append the assistant's tool_calls, then execute each call (tenant-scoped)
    # and inject the result as a tool-role message.
    augmented = list(messages)
    augmented.append(
        Message(
            role=MessageRole.ASSISTANT,
            content=response.content or "",
            tool_calls=tool_calls,
        )
    )

    result_records: List[Dict[str, Any]] = []
    executed_tools: List[Tool] = []
    for call in tool_calls:
        tool, result = execute_tool_call(call, organization_id, db)
        if tool is not None:
            executed_tools.append(tool)
        record = result.to_dict()
        record["tool_call_id"] = call.get("id")
        result_records.append(record)
        augmented.append(
            Message(
                role=MessageRole.TOOL,
                content=result.render(),
                tool_call_id=call.get("id"),
            )
        )

    logger.info(
        "function_calling_round_complete",
        organization_id=str(organization_id),
        selected=len(tool_calls),
        executed=len(executed_tools),
    )

    return FunctionCallingResult(
        tool_calls=tool_calls,
        tool_results=result_records,
        messages=augmented,
        called_tools=executed_tools,
    )


async def stream_final_answer(
    messages: List[Message],
    model_name: str,
    temperature: float = 0.2,
):
    """Stream the final grounded answer from the augmented message list.

    Yields text deltas. The provider is OpenAI-compatible, so it streams the
    assistant's natural-language answer (no further tool calls are requested).
    """
    provider = _provider(
        settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY or "",
        settings.OPENROUTER_BASE_URL,
    )
    try:
        async for chunk in provider.stream(
            GenerationRequest(
                messages=messages,
                model=model_name,
                temperature=temperature,
                max_tokens=1024,
                stream=True,
            )
        ):
            if chunk.delta_content:
                yield chunk.delta_content
    finally:
        await provider.close()


# ---------------------------------------------------------------------------
# Public re-exports used by the conversation pipeline
# ---------------------------------------------------------------------------


def function_calling_enabled(organization_id: uuid.UUID, db, agent=None) -> bool:
    """Whether a function-calling round should be attempted for this turn.

    True only when an LLM is configured (``rag_llm_enabled``) AND the tenant has
    at least one active tool available to the conversation. Keeps the offline
    RAG path completely unchanged when there is no LLM or no tools.
    """
    if not rag_llm_enabled():
        return False
    try:
        return bool(discover_tools(organization_id, db, agent))
    except Exception:
        return False


__all__ = [
    "generate_function_schema",
    "generate_function_schemas",
    "auto_select_tools",
    "validate_tool_arguments",
    "discover_tools",
    "parse_tool_call",
    "execute_tool_call",
    "run_function_calling",
    "stream_final_answer",
    "function_calling_enabled",
    "FunctionCallingResult",
    "build_sources",
    "compose_answer_offline",
    "retrieve_chunks_for_query",
    "rag_llm_enabled",
]
