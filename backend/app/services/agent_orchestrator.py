"""Agent Orchestrator (Milestone 4, Phase 4).

Coordinates multiple tenant agents to accomplish a higher-level goal, reusing
(rather than duplicating) the components delivered in earlier milestones:

* **Agent API / RepositoryFactory** (``app.repositories.tenant_repository``) --
  agents are discovered and resolved *within* ``organization_id``, so the
  orchestrator is tenant-scoped at the repository ``WHERE`` level. A step that
  references an agent from another tenant simply fails to resolve and is
  recovered (never cross-tenant executed).
* **Function Calling** (``app.services.function_calling``) -- each agent *step*
  is run through the exact same chat + tool-calling pipeline as a normal chat
  turn: tools are discovered via ``discover_tools`` and executed through
  ``run_function_calling`` -> the Tool Execution Engine. This is genuine reuse,
  not a second implementation.
* **Tool Registry + Tool Execution Engine** (``app.services.tool_registry``,
  ``app.services.tool_executor``) -- inherited automatically because every step
  runs through ``run_function_calling``.
* **RAG Pipeline** (``app.services.rag``) -- inherited inside ``run_function_calling``
  (the same context-building / retrieval path used by the chat pipeline).
* **Streaming Chat** (``app.ai.providers``) -- the final synthesised answer is
  produced with the same OpenAI-compatible provider; the endpoint streams it
  token-by-token reusing the conversation streaming pattern.

The orchestrator covers the four Phase 4 deliverables:

1. **Task Planning** -- ``plan_task`` asks the LLM to decompose a goal into an
   ordered set of ``PlanStep`` s (each targeting one agent, with explicit
   ``depends_on`` edges and optional ``parallel_group`` tags), and falls back to
   a deterministic single-step plan when no LLM is configured or planning fails.
2. **Agent-to-Agent Communication** -- the output of each completed step is
   threaded into the prompt of the steps that depend on it (the agent hand-off).
3. **Sequential & Parallel Execution** -- steps whose dependencies are all
   satisfied are run concurrently (``asyncio.gather``); a step that depends on
   another waits until it finishes. This yields both linear (sequential) and
   fan-out (parallel) execution naturally.
4. **Failure Recovery** -- each step is retried with exponential backoff up to
   ``max_retries``; a step that still fails is recorded as ``failed`` and the
   orchestrator either continues (feeding the error to downstream agents so they
   can adapt) or halts (skipping remaining steps) per ``halt_on_failure``.

All errors are contained per-step: a failed step never crashes the turn, and a
full ``OrchestrationResult`` (with ``status`` of ``completed`` or
``completed_with_errors``) is always produced.
"""
from __future__ import annotations

import asyncio
import json
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
from app.services.conversation_memory import ConversationMemoryService
from app.services.function_calling import (
    discover_tools,
    function_calling_enabled,
    run_function_calling,
    stream_final_answer,
)
from app.services.rag import rag_llm_enabled

logger = get_logger(__name__)

# Default number of retry attempts per step (beyond the first try).
_DEFAULT_MAX_RETRIES = 1
# Cap on the number of agents the planner may fan a goal across (keeps plans
# bounded and avoids runaway fan-out in large tenants).
_MAX_PLANNED_STEPS = 12


# ---------------------------------------------------------------------------
# Plan data model
# ---------------------------------------------------------------------------


@dataclass
class PlanStep:
    """A single unit of work in an orchestration plan.

    ``agent_ref`` identifies the tenant agent that should run the step, by
    ``public_id`` first, then case-insensitive name (resolved at execution time
    *within* the tenant). ``depends_on`` lists the ``step_id`` s that must
    complete before this step may run (sequential dependency). Steps with no
    dependencies run as soon as the executor starts. ``parallel_group`` is an
    optional tag: steps sharing a group run concurrently when ready (a hint for
    the planner; the executor derives concurrency purely from ``depends_on``).
    """

    step_id: str
    agent_ref: str
    instruction: str
    depends_on: List[str] = field(default_factory=list)
    parallel_group: Optional[str] = None
    max_retries: Optional[int] = None
    notes: Optional[str] = None


@dataclass
class TaskPlan:
    """An ordered, dependency-graph plan produced by the planner."""

    goal: str
    steps: List[PlanStep] = field(default_factory=list)

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    def step_ids(self) -> List[str]:
        return [s.step_id for s in self.steps]

    def roots(self) -> List[PlanStep]:
        """Steps with no dependencies (run first in parallel)."""
        return [s for s in self.steps if not s.depends_on]


@dataclass
class PlanStepResult:
    """Outcome of executing a single ``PlanStep``."""

    step_id: str
    agent_ref: str
    agent_id: Optional[str]
    status: str  # "success" | "failed" | "skipped"
    output: str
    error: Optional[str] = None
    error_type: Optional[str] = None
    attempts: int = 0
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0


@dataclass
class OrchestrationResult:
    """Aggregate outcome of running an entire orchestration plan."""

    goal: str
    plan: TaskPlan
    step_results: List[PlanStepResult] = field(default_factory=list)
    final_answer: str = ""
    status: str = "completed"  # "completed" | "completed_with_errors"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0

    def succeeded_steps(self) -> List[PlanStepResult]:
        return [r for r in self.step_results if r.status == "success"]

    def failed_steps(self) -> List[PlanStepResult]:
        return [r for r in self.step_results if r.status == "failed"]


# ---------------------------------------------------------------------------
# Plan parsing / validation
# ---------------------------------------------------------------------------


class PlanParseError(ValueError):
    """Raised when an LLM plan cannot be parsed into a valid ``TaskPlan``."""


def parse_plan(data: Any, agents: Optional[List[Agent]] = None) -> TaskPlan:
    """Parse a raw LLM plan (dict or JSON string) into a validated ``TaskPlan``.

    Expects a structure like::

        {"goal": "...", "steps": [
            {"step_id": "1", "agent": "<public_id or name>",
             "instruction": "...", "depends_on": [], "parallel_group": null}
        ]}

    Raises ``PlanParseError`` on malformed input so callers can fall back to a
    deterministic plan. ``goal`` defaults to "" when absent.
    """
    if isinstance(data, str):
        data = _extract_json(data)
    if not isinstance(data, dict):
        raise PlanParseError("plan must be a JSON object")

    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise PlanParseError("plan must contain a non-empty 'steps' list")

    goal = data.get("goal") or ""
    if not isinstance(goal, str):
        goal = str(goal)

    steps: List[PlanStep] = []
    seen_ids: set = set()
    for i, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise PlanParseError(f"step #{i} must be an object")
        step_id = str(raw.get("step_id") or (i + 1))
        if step_id in seen_ids:
            raise PlanParseError(f"duplicate step_id: {step_id}")
        seen_ids.add(step_id)

        agent_ref = raw.get("agent") or raw.get("agent_ref")
        if not agent_ref or not isinstance(agent_ref, str):
            raise PlanParseError(f"step {step_id} is missing an 'agent' reference")
        agent_ref = agent_ref.strip()

        instruction = raw.get("instruction")
        if instruction is None:
            instruction = goal
        if not isinstance(instruction, str):
            instruction = str(instruction)

        depends_on = raw.get("depends_on") or []
        if not isinstance(depends_on, list):
            raise PlanParseError(f"step {step_id} 'depends_on' must be a list")
        depends_on = [str(d) for d in depends_on]

        parallel_group = raw.get("parallel_group")
        if parallel_group is not None and not isinstance(parallel_group, str):
            parallel_group = str(parallel_group)

        max_retries = raw.get("max_retries")
        if max_retries is not None:
            try:
                max_retries = int(max_retries)
            except (TypeError, ValueError):
                max_retries = None

        steps.append(
            PlanStep(
                step_id=step_id,
                agent_ref=agent_ref,
                instruction=instruction,
                depends_on=depends_on,
                parallel_group=parallel_group,
                max_retries=max_retries,
                notes=raw.get("notes"),
            )
        )

    # Validate that every dependency references a real step in this plan.
    valid_ids = {s.step_id for s in steps}
    for s in steps:
        for dep in s.depends_on:
            if dep not in valid_ids:
                raise PlanParseError(
                    f"step {s.step_id} depends on unknown step '{dep}'"
                )

    return TaskPlan(goal=goal, steps=steps)


def _extract_json(text: str) -> Any:
    """Best-effort extraction of a JSON object from an LLM response.

    Strips markdown code fences and the surrounding prose so that a plan wrapped
    in ```json ... ``` (or free text) still parses.
    """
    if text is None:
        raise PlanParseError("empty plan text")
    cleaned = text.strip()
    # Strip a leading ```json / ``` fence.
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[: -3]
        cleaned = cleaned.strip()
    # Fall back to the outermost {...} block if there is stray prose.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise PlanParseError(f"invalid plan JSON: {exc}") from exc


def build_fallback_plan(goal: str, primary_agent: Optional[Agent]) -> TaskPlan:
    """Deterministic plan used when LLM planning is unavailable.

    Produces a single step that runs the supplied primary agent (or, if none, a
    synthetic step with an empty agent reference that the executor will mark
    failed). Keeps the orchestrator usable fully offline.
    """
    agent_ref = ""
    if primary_agent is not None:
        agent_ref = primary_agent.public_id or primary_agent.name or ""
    step = PlanStep(
        step_id="1",
        agent_ref=agent_ref,
        instruction=goal,
        depends_on=[],
        parallel_group=None,
        notes="deterministic fallback (no LLM planner)",
    )
    return TaskPlan(goal=goal, steps=[step])


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _elapsed_ms(started: datetime) -> float:
    return round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 3)


def _provider(api_key: str, base_url: str) -> BaseLLMProvider:
    """Construct the OpenAI-compatible chat provider (injectable for tests)."""
    return OpenRouterProvider(api_key=api_key, base_url=base_url)


class AgentOrchestrator:
    """Coordinates a set of tenant agents to fulfil a goal.

    The orchestrator is tenant-scoped by construction: it is created with an
    ``organization_id`` and a ``db`` session, and resolves every agent through
    the tenant-scoped ``AgentRepository``. It reuses the function-calling
    pipeline for each agent step, so tool execution, validation, and RAG context
    are inherited unchanged.
    """

    def __init__(
        self,
        organization_id: Any,
        db: Any = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        agents: Optional[List[Agent]] = None,
        conversation_id: Any = None,
    ):
        self.organization_id = organization_id
        self.db = db
        self.max_retries = max_retries
        self._agents_override = list(agents) if agents is not None else None
        self._agents_repo = (
            RepositoryFactory(db, organization_id).agents() if db is not None else None
        )
        # Conversation Memory (Milestone 5, Phase 1): reuse the memory service so
        # every agent step prompt can be enriched with prior conversation history
        # (with token budgeting) instead of duplicating persistence logic.
        self.conversation_id = conversation_id
        self._memory = (
            ConversationMemoryService(db, organization_id) if db is not None else None
        )

    # --- Public API ---------------------------------------------------------

    async def orchestrate(
        self,
        goal: str,
        *,
        primary_agent: Optional[Agent] = None,
        conversation_id: Optional[Any] = None,
        halt_on_failure: bool = False,
        max_retries: Optional[int] = None,
    ) -> OrchestrationResult:
        """Plan (if needed) and execute an orchestrated task for ``goal``.

        ``primary_agent`` is the agent that owns the conversation (used as the
        fallback planner target and as the synthesis voice). Returns a complete
        ``OrchestrationResult`` regardless of per-step failures.
        """
        agents = self._list_agents()
        plan = await self.plan_task(goal, agents, primary_agent=primary_agent)
        return await self.execute_plan(
            plan,
            goal,
            primary_agent=primary_agent,
            conversation_id=conversation_id,
            halt_on_failure=halt_on_failure,
            max_retries=max_retries,
        )

    def _with_history(self, text: str) -> str:
        """Prepend conversation history (token-budgeted) to ``text``.

        Returns ``text`` unchanged when memory is unavailable or no conversation
        is bound, so offline / conversation-less runs are unaffected.
        """
        if self._memory is not None and self.conversation_id is not None:
            enhanced, _ = self._memory.inject_conversation_history(
                self.conversation_id, text
            )
            return enhanced
        return text

    async def plan_task(
        self,
        goal: str,
        agents: List[Agent],
        primary_agent: Optional[Agent] = None,
    ) -> TaskPlan:
        """Decompose ``goal`` into a ``TaskPlan`` using the LLM planner.

        Falls back to :func:`build_fallback_plan` when no LLM is configured or
        planning fails, so the orchestrator always has a runnable plan.
        """
        if not rag_llm_enabled() or not agents:
            return build_fallback_plan(goal, primary_agent or (agents[0] if agents else None))

        try:
            provider = _provider(
                settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY or "",
                settings.OPENROUTER_BASE_URL,
            )
            try:
                request = GenerationRequest(
                    messages=[
                        Message(role=MessageRole.SYSTEM, content=_PLANNER_SYSTEM_PROMPT),
                        Message(
                            role=MessageRole.USER,
                            content=_planning_prompt(goal, agents),
                        ),
                    ],
                    model=settings.RAG_LLM_MODEL,
                    temperature=0.2,
                    max_tokens=1500,
                    json_mode=True,
                )
                response = await provider.generate(request)
            finally:
                await provider.close()

            plan = parse_plan(response.content, agents)
            if not plan.steps:
                raise PlanParseError("planner returned no steps")
            # Bound the plan size defensively.
            if len(plan.steps) > _MAX_PLANNED_STEPS:
                plan.steps = plan.steps[:_MAX_PLANNED_STEPS]
            return plan
        except Exception as exc:  # resilience: never let planning block a turn
            logger.warning(
                "orchestrator_planning_failed_fallback",
                organization_id=str(self.organization_id),
                error=str(exc),
            )
            return build_fallback_plan(
                goal, primary_agent or (agents[0] if agents else None)
            )

    async def execute_plan(
        self,
        plan: TaskPlan,
        goal: str,
        *,
        primary_agent: Optional[Agent] = None,
        conversation_id: Optional[Any] = None,
        halt_on_failure: bool = False,
        max_retries: Optional[int] = None,
    ) -> OrchestrationResult:
        """Execute ``plan``, running ready steps concurrently with retry and
        failure recovery. Returns the aggregate ``OrchestrationResult``.
        """
        if conversation_id is not None:
            self.conversation_id = conversation_id
        started = _now()
        retries = max_retries if max_retries is not None else self.max_retries

        agents_by_ref = self._build_agent_index()
        results: Dict[str, PlanStepResult] = {}
        completed: set = set()
        ordered: List[PlanStepResult] = []
        halted = False

        while len(completed) < len(plan.steps) and not halted:
            ready = [
                s
                for s in plan.steps
                if s.step_id not in completed
                and all(d in completed for d in s.depends_on)
            ]
            if not ready:
                # Remaining steps are unreachable (missing/cyclic dependency or a
                # prerequisite that never completed under halt mode).
                for s in plan.steps:
                    if s.step_id not in completed:
                        res = PlanStepResult(
                            step_id=s.step_id,
                            agent_ref=s.agent_ref,
                            agent_id=None,
                            status="skipped",
                            output="",
                            error="Unreachable: dependency not satisfied",
                            error_type="unreachable",
                            attempts=0,
                            depends_on=list(s.depends_on),
                            started_at=_now(),
                            duration_ms=0.0,
                        )
                        results[s.step_id] = res
                        ordered.append(res)
                        completed.add(s.step_id)
                break

            # Parallel execution: every currently-ready step runs concurrently.
            batch = await asyncio.gather(
                *[
                    self._execute_step_with_retry(s, goal, results, agents_by_ref, retries)
                    for s in ready
                ]
            )
            for res in batch:
                results[res.step_id] = res
                ordered.append(res)
                completed.add(res.step_id)
                if res.status == "failed" and halt_on_failure:
                    halted = True

            if halted:
                # Mark any not-yet-completed steps as skipped.
                for s in plan.steps:
                    if s.step_id not in completed:
                        res = PlanStepResult(
                            step_id=s.step_id,
                            agent_ref=s.agent_ref,
                            agent_id=None,
                            status="skipped",
                            output="",
                            error="Skipped: orchestration halted after a failure",
                            error_type="halted",
                            attempts=0,
                            depends_on=list(s.depends_on),
                            started_at=_now(),
                            duration_ms=0.0,
                        )
                        results[s.step_id] = res
                        ordered.append(res)
                        completed.add(s.step_id)

        failed = [r for r in ordered if r.status == "failed"]
        status = "completed" if not failed else "completed_with_errors"
        final_answer = await self._synthesize(goal, ordered, primary_agent)

        return OrchestrationResult(
            goal=goal,
            plan=plan,
            step_results=ordered,
            final_answer=final_answer,
            status=status,
            created_at=started,
            duration_ms=_elapsed_ms(started),
        )

    # --- Step execution -----------------------------------------------------

    async def _execute_step_with_retry(
        self,
        step: PlanStep,
        goal: str,
        results: Dict[str, PlanStepResult],
        agents_by_ref: Dict[str, Agent],
        max_retries: int,
    ) -> PlanStepResult:
        """Run one step with bounded retries (Failure Recovery)."""
        started = _now()
        agent = agents_by_ref.get(step.agent_ref)
        if agent is None:
            logger.warning(
                "orchestrator_agent_not_found",
                agent_ref=step.agent_ref,
                organization_id=str(self.organization_id),
            )
            return PlanStepResult(
                step_id=step.step_id,
                agent_ref=step.agent_ref,
                agent_id=None,
                status="failed",
                output="",
                error=f"Agent '{step.agent_ref}' not found in this tenant",
                error_type="agent_not_found",
                attempts=0,
                depends_on=list(step.depends_on),
                started_at=started,
                duration_ms=_elapsed_ms(started),
            )

        dep_context = self._build_dep_context(step, results)
        attempts = 0
        last_error: Optional[str] = None
        tries = (step.max_retries if step.max_retries is not None else max_retries) + 1

        for attempt in range(tries):
            attempts = attempt + 1
            try:
                output, tool_calls, tool_results = await self._run_agent_step(
                    step, goal, dep_context, agent
                )
                return PlanStepResult(
                    step_id=step.step_id,
                    agent_ref=step.agent_ref,
                    agent_id=str(agent.id),
                    status="success",
                    output=output or "",
                    error=None,
                    attempts=attempts,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    depends_on=list(step.depends_on),
                    started_at=started,
                    duration_ms=_elapsed_ms(started),
                )
            except Exception as exc:  # isolation: one step's failure is contained
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "orchestrator_step_failed",
                    step_id=step.step_id,
                    agent_ref=step.agent_ref,
                    attempt=attempts,
                    error=last_error,
                )
                if attempt < tries - 1:
                    # Exponential backoff (capped) before the next attempt.
                    await asyncio.sleep(min(0.05 * (2 ** attempt), 1.0))

        return PlanStepResult(
            step_id=step.step_id,
            agent_ref=step.agent_ref,
            agent_id=str(agent.id),
            status="failed",
            output="",
            error=last_error,
            error_type="execution_error",
            attempts=attempts,
            depends_on=list(step.depends_on),
            started_at=started,
            duration_ms=_elapsed_ms(started),
        )

    async def _run_agent_step(
        self,
        step: PlanStep,
        goal: str,
        dep_context: str,
        agent: Agent,
    ) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Run a single agent step, reusing the function-calling pipeline.

        Returns ``(output_text, tool_calls, tool_results)``. When the tenant/agent
        has active tools and an LLM is configured, the step is executed through
        ``run_function_calling`` (which performs tool auto-selection + execution
        via the Tool Execution Engine and RAG context building). Otherwise a
        plain generation is used.
        """
        instruction = step.instruction or goal
        user_content = self._step_user_prompt(goal, instruction, dep_context)
        # Conversation Memory (Milestone 5, Phase 1): inject prior conversation
        # history into the step prompt (token-budgeted) so each agent step is
        # grounded in the ongoing conversation.
        user_content = self._with_history(user_content)

        # Reuse the exact chat + function-calling pipeline (tools, RAG, engine).
        if self.db is not None and function_calling_enabled(
            self.organization_id, self.db, agent
        ):
            tools = discover_tools(self.organization_id, self.db, agent)
            fc = await run_function_calling(
                user_content,
                self.organization_id,
                self.db,
                agent.model_name,
                tools,
                scored=[],
                agent_system_prompt=agent.system_prompt,
            )
            text = "".join([d async for d in stream_final_answer(fc.messages, agent.model_name)])
            return text, fc.tool_calls, fc.tool_results

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
                            content=agent.system_prompt or _DEFAULT_STEP_SYSTEM,
                        ),
                        Message(role=MessageRole.USER, content=user_content),
                    ],
                    model=agent.model_name,
                    temperature=0.3,
                    max_tokens=1024,
                )
            )
        finally:
            await provider.close()
        return (response.content or ""), [], []

    # --- Synthesis ----------------------------------------------------------

    async def _synthesize(
        self,
        goal: str,
        ordered: List[PlanStepResult],
        primary_agent: Optional[Agent],
    ) -> str:
        """Combine successful step outputs into a final answer.

        Uses the LLM when configured (reuses the provider); otherwise joins the
        labelled outputs deterministically. A failed plan yields a clear note.
        """
        successful = [
            (r.agent_ref, r.output) for r in ordered if r.status == "success" and r.output
        ]
        if not successful:
            failed = [r for r in ordered if r.status == "failed"]
            if failed:
                return (
                    "The orchestrated task could not be completed: "
                    + "; ".join(f"step {r.step_id} ({r.agent_ref}) failed"
                               + (f" - {r.error}" if r.error else "")
                               for r in failed)
                )
            return "(No agent produced output for this task.)"

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
                                content=f"Goal: {goal}\n\nAgent outputs:\n{joined}",
                            ),
                        ],
                        model=(primary_agent.model_name if primary_agent else settings.RAG_LLM_MODEL),
                        temperature=0.2,
                        max_tokens=1024,
                    )
                )
            finally:
                await provider.close()
            return response.content or joined
        except Exception as exc:
            logger.warning("orchestrator_synthesis_failed", error=str(exc))
            return joined

    # --- Helpers ------------------------------------------------------------

    def _list_agents(self) -> List[Agent]:
        if self._agents_override is not None:
            return self._agents_override
        if self._agents_repo is None:
            return []
        return self._agents_repo.get_all()

    def _build_agent_index(self) -> Dict[str, Agent]:
        """Index agents by public_id and (case-insensitive) name for resolution.

        Resolution is performed purely within the tenant's repository result, so
        an agent from another organization can never match (tenant isolation).
        """
        index: Dict[str, Agent] = {}
        for agent in self._list_agents():
            if agent.public_id:
                index[agent.public_id] = agent
                index[agent.public_id.lower()] = agent
            if agent.name:
                index[agent.name] = agent
                index[agent.name.lower()] = agent
        return index

    def _build_dep_context(
        self, step: PlanStep, results: Dict[str, PlanStepResult]
    ) -> str:
        """Build the agent-to-agent hand-off context from completed deps.

        Failed dependencies are included as error context so downstream agents
        can attempt to recover rather than blindly failing.
        """
        parts: List[str] = []
        for dep in step.depends_on:
            res = results.get(dep)
            if res is None:
                continue
            if res.status == "success":
                parts.append(f"[Output from step {dep} / {res.agent_ref}]\n{res.output}")
            else:
                parts.append(
                    f"[Step {dep} / {res.agent_ref} FAILED"
                    + (f": {res.error}" if res.error else "")
                    + "] Proceed using your best judgement."
                )
        return "\n\n".join(parts)

    @staticmethod
    def _step_user_prompt(goal: str, instruction: str, dep_context: str) -> str:
        sections = [f"Overall goal: {goal}", f"Your task: {instruction}"]
        if dep_context:
            sections.append(f"Context from upstream agents:\n{dep_context}")
        sections.append("Produce a concise, self-contained result for your task.")
        return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Prompts (static)
# ---------------------------------------------------------------------------

_PLANNER_SYSTEM_PROMPT = (
    "You are a task planner for a multi-agent system. Given a high-level goal "
    "and the list of available agents, decompose the goal into a small ordered "
    "set of steps. Each step is assigned to exactly ONE agent and may depend on "
    "previous steps. Prefer 1-5 steps. Return ONLY a JSON object of the form "
    '{"goal": "<goal>", "steps": [{"step_id": "1", "agent": "<agent public_id>", '
    '"instruction": "<what this agent should do>", "depends_on": [], '
    '"parallel_group": null}]}. Use "depends_on" to sequence steps; steps with no '
    'dependencies run in parallel. Reference each agent by its "agent" public_id.'
)

_SYNTHESIS_SYSTEM_PROMPT = (
    "You are the lead coordinator. Combine the outputs of the agents below into "
    "a single coherent answer to the original goal. Be concise and cite which "
    "agent contributed what where relevant."
)

_DEFAULT_STEP_SYSTEM = "You are a helpful assistant executing one step of a larger task."

_PLANNING_INSTRUCTION_MARKER = "DECOMPOSE THE GOAL"


def _planning_prompt(goal: str, agents: List[Agent]) -> str:
    """Render the planner user prompt enumerating the tenant's available agents."""
    lines = [f"{_PLANNING_INSTRUCTION_MARKER}:", f"Goal: {goal}", "", "Available agents:"]
    for a in agents:
        ref = a.public_id or a.name
        desc = (a.description or "").strip() or "(no description)"
        lines.append(f"- public_id={ref} | name={a.name} | {desc}")
    lines.append("")
    lines.append("Return the JSON plan referencing each step's agent by public_id.")
    return "\n".join(lines)


__all__ = [
    "PlanStep",
    "TaskPlan",
    "PlanStepResult",
    "OrchestrationResult",
    "PlanParseError",
    "parse_plan",
    "build_fallback_plan",
    "AgentOrchestrator",
]
