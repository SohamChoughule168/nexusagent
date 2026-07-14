"""Schemas for the Multi-Agent Router (Milestone 4, Phase 5).

Lightweight Pydantic models for the routing request/response surface. The router
service (``app.services.multi_agent_router``) reuses the Agent Orchestrator,
Function Calling, Tool Execution and RAG pipelines, so these schemas only carry
routing-specific metadata (the decision, per-agent dispatch outputs, and the
final answer).
"""
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# Routing modes:
#   single     -> dispatch to the single best agent (top-1).
#   specialists-> dispatch to all selected agents in parallel, then synthesize.
#   orchestrate-> delegate coordination to the Agent Orchestrator (Phase 4 reuse).
#   auto       -> single when top_k == 1, else specialists.
_ROUTING_MODES = "^(auto|single|specialists|orchestrate)$"


class RouteRequest(BaseModel):
    """Request body for ``POST /conversations/{id}/route``.

    Routes ``query`` across the authenticated tenant's agents using the named
    routing ``policy`` (or the default composite policy), then dispatches to the
    selected agent(s) and returns/streams the result.
    """

    query: str = Field(..., min_length=1, description="The user query to route")
    policy: Optional[str] = Field(
        default=None,
        description=(
            "Routing policy name: 'keyword', 'capability', 'llm', "
            "'round_robin' or 'composite'. Falls back to the default "
            "composite policy when omitted/invalid."
        ),
    )
    top_k: int = Field(
        default=1,
        ge=1,
        le=8,
        description="Maximum number of agents to select for dispatch.",
    )
    mode: str = Field(
        default="auto",
        pattern=_ROUTING_MODES,
        description="Dispatch strategy: auto | single | specialists | orchestrate.",
    )
    halt_on_failure: bool = Field(
        default=False,
        description="(orchestrate mode) Stop and skip remaining agents after a failure.",
    )
    max_retries: int = Field(
        default=1,
        ge=0,
        le=5,
        description="(orchestrate mode) Retries per dispatched agent step.",
    )


class AgentScoreSchema(BaseModel):
    agent_ref: str
    agent_id: Optional[str] = None
    name: Optional[str] = None
    score: float
    rationale: str


class RoutingDecisionSchema(BaseModel):
    query: str
    policy_name: str
    fallback_used: bool
    selected: List[AgentScoreSchema] = []
    candidates: List[AgentScoreSchema] = []


class AgentDispatchOutputSchema(BaseModel):
    agent_ref: str
    agent_id: Optional[str] = None
    name: Optional[str] = None
    status: str  # "success" | "failed"
    output: str
    error: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = []
    tool_results: List[Dict[str, Any]] = []


class RouterResultSchema(BaseModel):
    query: str
    decision: RoutingDecisionSchema
    answer: str
    status: str  # "completed" | "completed_with_errors" | "no_agents"
    mode: str
    outputs: List[AgentDispatchOutputSchema] = []


class RouteEvent(BaseModel):
    """One NDJSON line emitted by the streaming route endpoint."""

    type: str  # "decision" | "dispatch_result" | "token" | "done" | "error"
    data: Dict[str, Any] = {}
