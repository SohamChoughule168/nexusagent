"""Multi-Agent Router (Milestone 4, Phase 5).

Routes an incoming query to the most appropriate tenant agent(s), then
dynamically dispatches to them and coordinates the results. The router is a
*thin coordinator* that reuses (rather than duplicates) every component built in
earlier milestones:

* **Agent Orchestrator** (``app.services.agent_orchestrator``) -- the
  ``orchestrate`` dispatch ``mode`` hands the routing decision's selected agents
  to the orchestrator for multi-step, parallel, failure-recovering coordination.
  Routing is the *front door* that picks the agents; the orchestrator runs them.
  No second agent-execution engine is introduced.
* **Function Calling** (``app.services.function_calling``) -- every dispatched
  agent runs through the exact same ``discover_tools`` -> ``run_function_calling``
  -> ``stream_final_answer`` pipeline as a normal chat turn. Tool auto-selection,
  execution, validation and RAG context building are all inherited unchanged.
* **Tool Registry + Tool Execution Engine** -- inherited via function calling.
* **RAG Pipeline** -- inherited inside ``run_function_calling``.
* **Streaming Chat** (``app.ai.providers``) -- the OpenAI-compatible provider
  produces each agent's answer; the endpoint streams it token-by-token.
* **RepositoryFactory + TenantContext** -- agents and tools are always resolved
  *within* ``organization_id`` derived from the authenticated principal, so
  tenant isolation is preserved at every boundary (a routing decision can never
  address another organization's agent, because selection only sees this
  tenant's agents).

Phase 5 deliverables covered:

1. **Multi-Agent Router** -- :class:`MultiAgentRouter` ties selection +
   dispatch + coordination together and returns a complete ``RouterResult``.
2. **Agent Selection** -- :class:`AgentSelector` ranks the tenant's agents for a
   query via a pluggable :class:`RoutingPolicy` and produces a
   :class:`RoutingDecision` (selected agents + full candidate ranking).
3. **Routing Policies** -- a family of policies (keyword, capability, LLM intent
   classification, round-robin dynamic dispatch, and a weighted composite) plus a
   deterministic fallback, all swappable per request.
4. **Dynamic Dispatch** -- the router selects agents *at request time* from the
   live tenant agent set; round-robin provides load-balanced dynamic dispatch;
   dispatch reuses the function-calling pipeline per agent.
5. **Specialist Agent Coordination** -- when multiple specialists are selected
   (``specialists``/``auto`` with ``top_k > 1``) the router dispatches them in
   parallel and synthesizes a single answer; the ``orchestrate`` mode coordinates
   them via the Agent Orchestrator.

All errors are contained per-agent: a failed dispatch never crashes the turn, and
a full ``RouterResult`` (``completed`` or ``completed_with_errors``) is always
produced.
"""
from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
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
from app.models.all_models import Agent
from app.repositories.tenant_repository import RepositoryFactory
from app.services.agent_orchestrator import (
    AgentOrchestrator,
    PlanStep,
    TaskPlan,
)
from app.services.function_calling import (
    discover_tools,
    function_calling_enabled,
    run_function_calling,
    stream_final_answer,
)
from app.services.rag import rag_llm_enabled

logger = get_logger(__name__)

# Default weights for the composite policy (keyword + capability). The LLM
# policy is intentionally *not* in the default composite so routing stays
# deterministic and offline by default; callers opt in via ``policy="llm"``.
_COMPOSITE_KEYWORD_WEIGHT = 0.6
_COMPOSITE_CAPABILITY_WEIGHT = 0.4


# ---------------------------------------------------------------------------
# Scoring primitives
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set:
    """Lowercase word tokens of length > 2 (mirrors tool/agent auto-selection)."""
    if not text:
        return set()
    return {tok for tok in re.split(r"\W+", text.lower()) if len(tok) > 2}


@dataclass
class AgentScore:
    """A single agent's suitability score for a query."""

    agent_ref: str
    score: float
    rationale: str
    agent_id: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_ref": self.agent_ref,
            "agent_id": self.agent_id,
            "name": self.name,
            "score": round(self.score, 4),
            "rationale": self.rationale,
        }


@dataclass
class RoutingDecision:
    """The outcome of selecting agent(s) for a query."""

    query: str
    policy_name: str
    selected: List[AgentScore]
    candidates: List[AgentScore] = field(default_factory=list)
    fallback_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "policy_name": self.policy_name,
            "fallback_used": self.fallback_used,
            "selected": [s.to_dict() for s in self.selected],
            "candidates": [s.to_dict() for s in self.candidates],
        }


@dataclass
class AgentDispatchOutput:
    """The outcome of dispatching one agent for a query."""

    agent_ref: str
    status: str  # "success" | "failed"
    output: str
    agent_id: Optional[str] = None
    name: Optional[str] = None
    error: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_ref": self.agent_ref,
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results,
        }


@dataclass
class RouterResult:
    """Aggregate outcome of routing + dispatching a query."""

    query: str
    decision: RoutingDecision
    answer: str
    status: str  # "completed" | "completed_with_errors" | "no_agents"
    mode: str
    outputs: List[AgentDispatchOutput] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "decision": self.decision.to_dict(),
            "answer": self.answer,
            "status": self.status,
            "mode": self.mode,
            "outputs": [o.to_dict() for o in self.outputs],
            "duration_ms": self.duration_ms,
        }


# ---------------------------------------------------------------------------
# Routing Policies
# ---------------------------------------------------------------------------


class RoutingPolicy(ABC):
    """Base class for a strategy that scores tenant agents for a query."""

    name: str = "base"

    @abstractmethod
    async def select(
        self,
        query: str,
        agents: List[Agent],
        *,
        organization_id: Any = None,
        db: Any = None,
    ) -> List[AgentScore]:
        """Return all candidate agents ranked by suitability (descending)."""
        raise NotImplementedError


def _agent_ref(agent: Agent) -> str:
    """The reference key used to resolve an agent during dispatch."""
    return agent.public_id or agent.name or str(agent.id)


def _agent_text(agent: Agent) -> str:
    """Free-text surface of an agent used for keyword overlap scoring."""
    parts = [
        agent.name or "",
        agent.description or "",
        agent.system_prompt or "",
    ]
    return " ".join(parts).lower()


def _capability_tokens(agent: Agent) -> set:
    """Capability tokens declared on an agent (config-driven).

    Reads ``capabilities``, ``specialties``, ``topics``, ``expertise``, ``tags``
    and ``domains`` from ``agent.config`` (each may be a list or a comma/space
    separated string) so a routing policy can match a query against what the
    agent is *declared* to be good at, independent of its description prose.
    """
    config = getattr(agent, "config", None) or {}
    tokens: set = set()
    for key in ("capabilities", "specialties", "topics", "expertise", "tags", "domains"):
        value = config.get(key)
        if not value:
            continue
        if isinstance(value, (list, tuple, set)):
            for item in value:
                tokens.update(_tokenize(str(item)))
        else:
            tokens.update(_tokenize(str(value)))
    return tokens


def _score_to_agent(score: float, agent: Agent, rationale: str) -> AgentScore:
    return AgentScore(
        agent_ref=_agent_ref(agent),
        score=score,
        rationale=rationale,
        agent_id=str(agent.id),
        name=agent.name,
    )


class KeywordRoutingPolicy(RoutingPolicy):
    """Score agents by keyword overlap between the query and the agent's
    name/description/system-prompt text. Deterministic and offline; the default
    fallback when any richer policy fails.
    """

    name = "keyword"

    async def select(self, query, agents, *, organization_id=None, db=None):
        q_tokens = _tokenize(query)
        scores: List[AgentScore] = []
        if not q_tokens or not agents:
            return scores
        for agent in agents:
            text = _agent_text(agent)
            overlap = sum(1 for tok in q_tokens if tok in text)
            rationale = f"keyword overlap={overlap} of {len(q_tokens)} query tokens"
            scores.append(_score_to_agent(float(overlap), agent, rationale))
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores


class CapabilityRoutingPolicy(RoutingPolicy):
    """Score agents by overlap between the query and the agent's declared
    capabilities (``config.capabilities`` / ``specialties`` / ``topics`` / ...).

    Lets operators steer routing via structured agent metadata instead of hoping
    the description prose contains the right keywords.
    """

    name = "capability"

    async def select(self, query, agents, *, organization_id=None, db=None):
        q_tokens = _tokenize(query)
        scores: List[AgentScore] = []
        if not q_tokens or not agents:
            return scores
        for agent in agents:
            caps = _capability_tokens(agent)
            matched = [tok for tok in q_tokens if tok in caps]
            overlap = len(matched)
            rationale = (
                f"capability match={overlap} ({', '.join(sorted(matched))})"
                if matched
                else "no capability match"
            )
            scores.append(_score_to_agent(float(overlap), agent, rationale))
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores


class RoundRobinRoutingPolicy(RoutingPolicy):
    """Dynamic-dispatch / load-balancing policy.

    Maintains a per-tenant cursor and returns the next agent in rotation as the
    single top candidate (with all agents listed in rotated order as the
    candidate set). No scoring: it spreads load across agents over successive
    calls. The cursor is keyed by ``organization_id`` so each tenant balances
    independently; cross-tenant calls can never collide because agents are
    resolved only within the tenant.
    """

    name = "round_robin"
    _cursors: Dict[str, int] = {}

    async def select(self, query, agents, *, organization_id=None, db=None):
        scores: List[AgentScore] = []
        if not agents:
            return scores
        org_key = str(organization_id) if organization_id is not None else "__shared__"
        idx = RoundRobinRoutingPolicy._cursors.get(org_key, 0) % len(agents)
        RoundRobinRoutingPolicy._cursors[org_key] = (idx + 1) % len(agents)

        for offset in range(len(agents)):
            pos = (idx + offset) % len(agents)
            agent = agents[pos]
            is_pick = offset == 0
            rationale = (
                "round-robin dispatch (next agent in rotation)"
                if is_pick
                else "round-robin rotation candidate"
            )
            scores.append(_score_to_agent(1.0 if is_pick else 0.0, agent, rationale))
        # Selected (pick) first.
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores


class LLMRoutingPolicy(RoutingPolicy):
    """Intent-classification policy: asks the LLM to route the query to the best
    matching agent (by ``public_id``) and explain why. Falls back to the keyword
    policy when no LLM is configured or the classification fails, so routing is
    always resolvable.
    """

    name = "llm"

    async def select(self, query, agents, *, organization_id=None, db=None):
        if not rag_llm_enabled() or not agents:
            # Offline -> deterministic keyword fallback.
            return await KeywordRoutingPolicy().select(
                query, agents, organization_id=organization_id, db=db
            )
        try:
            provider = _provider(
                settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY or "",
                settings.OPENROUTER_BASE_URL,
            )
            try:
                response = await provider.generate(
                    GenerationRequest(
                        messages=[
                            Message(role=MessageRole.SYSTEM, content=_ROUTER_SYSTEM_PROMPT),
                            Message(role=MessageRole.USER, content=_routing_prompt(query, agents)),
                        ],
                        model=settings.RAG_LLM_MODEL,
                        temperature=0.0,
                        max_tokens=400,
                        json_mode=True,
                    )
                )
            finally:
                await provider.close()

            payload = _extract_json(response.content)
            chosen_ref = str(payload.get("agent_ref") or payload.get("agent") or "").strip()
            rationale = str(payload.get("rationale") or "llm intent classification")
            # Best match: chosen agent gets 1.0; everyone else 0.0 (so top_k=1
            # selects exactly the LLM's pick without arbitrary tie-breaking).
            scores: List[AgentScore] = []
            for agent in agents:
                is_pick = _agent_ref(agent) == chosen_ref
                scores.append(
                    _score_to_agent(
                        1.0 if is_pick else 0.0,
                        agent,
                        rationale if is_pick else "not selected by llm",
                    )
                )
            scores.sort(key=lambda s: s.score, reverse=True)
            # If the LLM picked something we cannot resolve, fall back to keyword.
            if not any(s.score > 0 for s in scores):
                logger.warning(
                    "router_llm_unresolved_fallback",
                    chosen_ref=chosen_ref,
                    organization_id=str(organization_id),
                )
                return await KeywordRoutingPolicy().select(
                    query, agents, organization_id=organization_id, db=db
                )
            return scores
        except Exception as exc:  # resilience: never let routing block a turn
            logger.warning("router_llm_failed_fallback", error=str(exc))
            return await KeywordRoutingPolicy().select(
                query, agents, organization_id=organization_id, db=db
            )


class CompositeRoutingPolicy(RoutingPolicy):
    """Weighted combination of multiple policies (the configurable "Routing
    Policies" deliverable). Each sub-policy's scores are normalized to ``[0,1]``
    (by its own max) and summed with the supplied weights. A deterministic
    fallback is used if every sub-policy errors.
    """

    name = "composite"

    def __init__(
        self,
        policies: List[Tuple[RoutingPolicy, float]],
        fallback: Optional[RoutingPolicy] = None,
    ):
        self._policies = policies
        self._fallback = fallback or KeywordRoutingPolicy()

    async def select(self, query, agents, *, organization_id=None, db=None):
        if not agents:
            return []
        combined: Dict[str, Dict[str, Any]] = {}
        any_ok = False
        for policy, weight in self._policies:
            try:
                sub = await policy.select(
                    query, agents, organization_id=organization_id, db=db
                )
            except Exception:
                sub = []
            if not sub:
                continue
            any_ok = True
            max_score = max((s.score for s in sub), default=0.0)
            for s in sub:
                norm = (s.score / max_score) if max_score > 0 else 0.0
                entry = combined.setdefault(
                    s.agent_ref,
                    {
                        "agent": s,
                        "contrib": [],
                        "score": 0.0,
                        "agent_id": s.agent_id,
                        "name": s.name,
                    },
                )
                entry["score"] += weight * norm
                entry["contrib"].append(f"{policy.name}={s.score:.2f}")

        if not any_ok:
            return await self._fallback.select(
                query, agents, organization_id=organization_id, db=db
            )

        scores: List[AgentScore] = []
        for ref, entry in combined.items():
            scores.append(
                AgentScore(
                    agent_ref=ref,
                    score=entry["score"],
                    rationale="; ".join(entry["contrib"]),
                    agent_id=entry["agent_id"],
                    name=entry["name"],
                )
            )
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores


# ---------------------------------------------------------------------------
# Agent Selector
# ---------------------------------------------------------------------------


class AgentSelector:
    """Selects the best agent(s) for a query via a named :class:`RoutingPolicy`.

    Builds a registry of policies (keyword, capability, llm, round_robin,
    composite) and resolves a per-request ``policy`` name to one of them. If the
    chosen policy errors, it transparently falls back to the deterministic
    keyword policy and flags ``fallback_used`` on the decision.
    """

    def __init__(
        self,
        policies: Optional[Dict[str, RoutingPolicy]] = None,
        default_policy: str = "composite",
    ):
        self._policies = policies or self._default_policies()
        self._default_policy = default_policy
        if default_policy not in self._policies:
            self._default_policy = "composite" if "composite" in self._policies else next(
                iter(self._policies)
            )

    @staticmethod
    def _default_policies() -> Dict[str, RoutingPolicy]:
        keyword = KeywordRoutingPolicy()
        capability = CapabilityRoutingPolicy()
        composite = CompositeRoutingPolicy(
            [
                (keyword, _COMPOSITE_KEYWORD_WEIGHT),
                (capability, _COMPOSITE_CAPABILITY_WEIGHT),
            ]
        )
        return {
            "keyword": keyword,
            "capability": capability,
            "llm": LLMRoutingPolicy(),
            "round_robin": RoundRobinRoutingPolicy(),
            "composite": composite,
        }

    def available_policies(self) -> List[str]:
        return sorted(self._policies.keys())

    async def select(
        self,
        query: str,
        agents: List[Agent],
        *,
        organization_id: Any = None,
        db: Any = None,
        policy: Optional[str] = None,
        top_k: int = 1,
    ) -> RoutingDecision:
        name = policy if policy in self._policies else self._default_policy
        pol = self._policies[name]
        fallback_used = False
        try:
            scores = await pol.select(
                query, agents, organization_id=organization_id, db=db
            )
        except Exception as exc:
            logger.warning("router_policy_failed_fallback", policy=name, error=str(exc))
            scores = await self._policies["keyword"].select(
                query, agents, organization_id=organization_id, db=db
            )
            fallback_used = True

        candidates = sorted(scores, key=lambda s: s.score, reverse=True)
        k = max(1, top_k)
        selected = candidates[:k]
        # When the policy produced no positive score (e.g. zero keyword overlap)
        # but agents exist, still pick the top candidate so dispatch never has an
        # empty selection -- routing degrades gracefully rather than aborting.
        if not selected and candidates:
            selected = candidates[:k]
        return RoutingDecision(
            query=query,
            policy_name=name,
            selected=selected,
            candidates=candidates,
            fallback_used=fallback_used,
        )


# ---------------------------------------------------------------------------
# Multi-Agent Router
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _elapsed_ms(started: datetime) -> float:
    return round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 3)


def _provider(api_key: str, base_url: str) -> BaseLLMProvider:
    """Construct the OpenAI-compatible chat provider (injectable for tests)."""
    return OpenRouterProvider(api_key=api_key, base_url=base_url)


_ROUTER_SYSTEM_PROMPT = (
    "You are a query router for a multi-agent system. Given a user query and the "
    "list of available agents (each with a public_id, name and description), "
    "choose the SINGLE best agent to handle the query. Return ONLY a JSON object "
    'of the form {"agent_ref": "<agent public_id>", "rationale": "<short reason>"}. '
    "Reference the agent by its public_id exactly."
)

_SYNTHESIS_SYSTEM_PROMPT = (
    "You are the lead coordinator. Combine the outputs of the specialist agents "
    "below into a single coherent answer to the user's query. Be concise and cite "
    "which agent contributed what where relevant."
)


def _routing_prompt(query: str, agents: List[Agent]) -> str:
    lines = [f"Route this query: {query}", "", "Available agents:"]
    for a in agents:
        ref = a.public_id or a.name
        desc = (a.description or "").strip() or "(no description)"
        caps = sorted(_capability_tokens(a))
        cap_note = f" | capabilities: {', '.join(caps)}" if caps else ""
        lines.append(f"- public_id={ref} | name={a.name} | {desc}{cap_note}")
    lines.append("")
    lines.append("Return the JSON routing decision referencing the agent public_id.")
    return "\n".join(lines)


def _extract_json(text: str) -> Dict[str, Any]:
    """Best-effort JSON object extraction from an LLM response."""
    if not text:
        return {}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[: -3]
        cleaned = cleaned.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        data = __import__("json").loads(cleaned)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class MultiAgentRouter:
    """Routes a query to the best tenant agent(s) and dispatches to them.

    Tenant-scoped by construction: built with an ``organization_id`` and optional
    ``db`` session; every agent/tool is resolved through the tenant-scoped
    repositories. Reuses the function-calling pipeline for each dispatch and the
    Agent Orchestrator for the ``orchestrate`` mode.
    """

    def __init__(
        self,
        organization_id: Any,
        db: Any = None,
        selector: Optional[AgentSelector] = None,
        agents: Optional[List[Agent]] = None,
    ):
        self.organization_id = organization_id
        self.db = db
        self._selector = selector or AgentSelector()
        self._agents_override = list(agents) if agents is not None else None
        self._agents_repo = (
            RepositoryFactory(db, organization_id).agents() if db is not None else None
        )

    # --- Public API ---------------------------------------------------------

    async def route(
        self,
        query: str,
        *,
        conversation_id: Any = None,
        primary_agent: Optional[Agent] = None,
        policy: Optional[str] = None,
        top_k: int = 1,
        mode: str = "auto",
        halt_on_failure: bool = False,
        max_retries: int = 1,
    ) -> RouterResult:
        """Select agent(s) for ``query`` and dispatch to them.

        ``mode``:
          * ``single``      -> dispatch to the top-1 agent.
          * ``specialists`` -> dispatch to all selected agents in parallel, then
            synthesize a single answer (specialist coordination).
          * ``orchestrate`` -> hand the selected agents to the Agent Orchestrator
            for coordinated, failure-recovering execution (Phase 4 reuse).
          * ``auto`` (default) -> ``single`` when ``top_k == 1``, else
            ``specialists``.
        """
        started = _now()
        agents = self._list_agents()

        if not agents:
            return RouterResult(
                query=query,
                decision=RoutingDecision(
                    query=query,
                    policy_name=policy or self._selector._default_policy,
                    selected=[],
                    candidates=[],
                    fallback_used=False,
                ),
                answer="No agents are available in this tenant to route the query to.",
                status="no_agents",
                mode=mode,
                outputs=[],
                duration_ms=_elapsed_ms(started),
            )

        decision = await self._selector.select(
            query,
            agents,
            organization_id=self.organization_id,
            db=self.db,
            policy=policy,
            top_k=top_k,
        )

        effective_mode = mode if mode != "auto" else ("single" if top_k <= 1 else "specialists")

        if effective_mode == "orchestrate":
            result = await self._route_orchestrate(
                query, decision, primary_agent, halt_on_failure, max_retries
            )
        else:
            outputs, answer = await self._route_dispatch(
                query, decision, effective_mode == "specialists"
            )
            failed = [o for o in outputs if o.status == "failed"]
            status = "completed" if not failed else "completed_with_errors"
            result = RouterResult(
                query=query,
                decision=decision,
                answer=answer,
                status=status,
                mode=effective_mode,
                outputs=outputs,
                duration_ms=_elapsed_ms(started),
            )

        return result

    # --- Agent listing / resolution ----------------------------------------

    def _list_agents(self) -> List[Agent]:
        if self._agents_override is not None:
            return self._agents_override
        if self._agents_repo is None:
            return []
        return self._agents_repo.get_all()

    def _build_agent_index(self) -> Dict[str, Agent]:
        """Resolve agents by public_id and (case-insensitive) name within the
        tenant's own agent set -- an agent from another tenant can never match
        (tenant isolation at agent selection).
        """
        index: Dict[str, Agent] = {}
        for agent in self._list_agents():
            ref = _agent_ref(agent)
            index[ref] = agent
            index[ref.lower()] = agent
            if agent.name:
                index[agent.name] = agent
                index[agent.name.lower()] = agent
        return index

    # --- Dispatch -----------------------------------------------------------

    async def _route_dispatch(
        self, query: str, decision: RoutingDecision, parallel: bool
    ) -> Tuple[List[AgentDispatchOutput], str]:
        """Direct dispatch to the selected agent(s) via the function-calling
        pipeline. When ``parallel`` (specialists mode), dispatched concurrently
        and their outputs synthesized into one answer.
        """
        agents_by_ref = self._build_agent_index()
        targets = decision.selected
        if not targets:
            return [], ""

        if parallel:
            dispatched = await asyncio.gather(
                *[self._dispatch_agent(agents_by_ref.get(t.agent_ref), query) for t in targets]
            )
            outputs = [
                self._to_output(t, res) for t, res in zip(targets, dispatched)
            ]
            answer = await self._synthesize(query, outputs)
            return outputs, answer

        # Single dispatch.
        target = targets[0]
        agent = agents_by_ref.get(target.agent_ref)
        output = self._to_output(
            target, await self._dispatch_agent(agent, query)
        )
        return [output], output.output

    async def _dispatch_agent(
        self, agent: Optional[Agent], query: str
    ) -> Tuple[str, str, List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
        """Run one agent on ``query`` through the function-calling pipeline.

        Returns ``(output_text, status, tool_calls, tool_results, error)``. A
        missing/unknown agent (shouldn't happen post-selection) is contained as a
        failed dispatch rather than raised. Mirrors the orchestrator's
        ``_run_agent_step`` so tool execution, validation and RAG are inherited.
        """
        if agent is None:
            return "", "failed", [], [], "Agent not found in this tenant"

        model = agent.model_name
        user_content = self._agent_prompt(query)
        try:
            if self.db is not None and function_calling_enabled(
                self.organization_id, self.db, agent
            ):
                tools = discover_tools(self.organization_id, self.db, agent)
                fc = await run_function_calling(
                    user_content,
                    self.organization_id,
                    self.db,
                    model,
                    tools,
                    scored=[],
                    agent_system_prompt=agent.system_prompt,
                )
                text = "".join([d async for d in stream_final_answer(fc.messages, model)])
                return text, "success", fc.tool_calls, fc.tool_results, None

            # Plain generation path (no tools / no LLM-injected tool calls).
            provider = _provider(
                settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY or "",
                settings.OPENROUTER_BASE_URL,
            )
            try:
                response = await provider.generate(
                    GenerationRequest(
                        messages=[
                            Message(
                                role=MessageRole.SYSTEM,
                                content=agent.system_prompt or "You are a helpful assistant.",
                            ),
                            Message(role=MessageRole.USER, content=user_content),
                        ],
                        model=model,
                        temperature=0.3,
                        max_tokens=1024,
                    )
                )
            finally:
                await provider.close()
            return (response.content or ""), "success", [], [], None
        except Exception as exc:
            logger.warning(
                "router_dispatch_failed",
                agent_ref=_agent_ref(agent) if agent else None,
                organization_id=str(self.organization_id),
                error=str(exc),
            )
            return "", "failed", [], [], f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _to_output(
        score: AgentScore,
        dispatch: Tuple[str, str, List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]],
    ) -> AgentDispatchOutput:
        output, status, tool_calls, tool_results, error = dispatch
        return AgentDispatchOutput(
            agent_ref=score.agent_ref,
            agent_id=score.agent_id,
            name=score.name,
            status=status,
            output=output or (error or ""),
            error=error,
            tool_calls=tool_calls,
            tool_results=tool_results,
        )

    async def _route_orchestrate(
        self,
        query: str,
        decision: RoutingDecision,
        primary_agent: Optional[Agent],
        halt_on_failure: bool,
        max_retries: int,
    ) -> RouterResult:
        """Delegate coordination of the selected agents to the Agent Orchestrator
        (Phase 4 reuse). The router's job ends at agent selection; the
        orchestrator runs them with parallel scheduling + failure recovery.
        """
        steps = [
            PlanStep(step_id=str(i + 1), agent_ref=s.agent_ref, instruction=query)
            for i, s in enumerate(decision.selected)
        ]
        plan = TaskPlan(goal=query, steps=steps)
        orch = AgentOrchestrator(
            self.organization_id, self.db, max_retries=max_retries
        )
        orch_result = await orch.execute_plan(
            plan,
            query,
            primary_agent=primary_agent,
            halt_on_failure=halt_on_failure,
            max_retries=max_retries,
        )

        outputs = [
            AgentDispatchOutput(
                agent_ref=r.agent_ref,
                agent_id=r.agent_id,
                status=r.status,
                output=r.output,
                error=r.error,
                tool_calls=r.tool_calls,
                tool_results=r.tool_results,
            )
            for r in orch_result.step_results
        ]
        return RouterResult(
            query=query,
            decision=decision,
            answer=orch_result.final_answer or "",
            status=orch_result.status,
            mode="orchestrate",
            outputs=outputs,
            duration_ms=orch_result.duration_ms,
        )

    async def _synthesize(
        self, goal: str, outputs: List[AgentDispatchOutput]
    ) -> str:
        """Combine successful specialist outputs into one answer.

        Uses the LLM when configured; otherwise joins labelled outputs
        deterministically. Failed specialists are noted so partly-failed
        coordination still yields a useful answer.
        """
        successful = [
            (o.agent_ref, o.output) for o in outputs if o.status == "success" and o.output
        ]
        if not successful:
            failed = [o for o in outputs if o.status == "failed"]
            if failed:
                return "Routing could not complete: " + "; ".join(
                    f"{o.agent_ref} failed" + (f" - {o.error}" if o.error else "")
                    for o in failed
                )
            return "(No agent produced output for this query.)"

        joined = "\n\n".join(f"[{ref}] {out}" for ref, out in successful)
        if not rag_llm_enabled():
            return joined
        try:
            provider = _provider(
                settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY or "",
                settings.OPENROUTER_BASE_URL,
            )
            try:
                response = await provider.generate(
                    GenerationRequest(
                        messages=[
                            Message(role=MessageRole.SYSTEM, content=_SYNTHESIS_SYSTEM_PROMPT),
                            Message(
                                role=MessageRole.USER,
                                content=f"Query: {goal}\n\nAgent outputs:\n{joined}",
                            ),
                        ],
                        model=settings.RAG_LLM_MODEL,
                        temperature=0.2,
                        max_tokens=1024,
                    )
                )
            finally:
                await provider.close()
            return response.content or joined
        except Exception as exc:
            logger.warning("router_synthesis_failed", error=str(exc))
            return joined

    @staticmethod
    def _agent_prompt(query: str) -> str:
        return (
            f"User query: {query}\n\n"
            "Produce a concise, self-contained response to the user's query."
        )


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------


__all__ = [
    "AgentScore",
    "RoutingDecision",
    "AgentDispatchOutput",
    "RouterResult",
    "RoutingPolicy",
    "KeywordRoutingPolicy",
    "CapabilityRoutingPolicy",
    "RoundRobinRoutingPolicy",
    "LLMRoutingPolicy",
    "CompositeRoutingPolicy",
    "AgentSelector",
    "MultiAgentRouter",
]
