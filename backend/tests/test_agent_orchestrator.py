"""Agent Orchestrator tests (Milestone 4, Phase 4).

Covers the four Phase 4 deliverables:

* **Task Planning** -- ``parse_plan`` validation, ``_extract_json`` fence
  stripping, and the deterministic fallback planner (offline-safe).
* **Agent-to-Agent Communication** -- a dependent step receives the upstream
  step's output (and a failed upstream step's error) as context.
* **Sequential & Parallel Execution** -- dependency edges drive sequential
  ordering; independent roots run concurrently (proven via in-flight tracking).
* **Failure Recovery** -- per-step retry with backoff, graceful degradation
  (downstream keeps running with error context), and ``halt_on_failure``
  short-circuiting.

Plus integration through ``POST /conversations/{id}/orchestrate`` (mocked LLM)
exercising the full plan -> execute -> persist -> stream flow and verifying
tenant isolation at the execution boundary and agent resolution.

These tests are written synchronously (``asyncio.run``) so they run in the
existing backend environment without requiring ``pytest-asyncio``.
"""
import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.ai.providers.base import GenerationResponse, StreamChunk
from app.main import app
from app.models.all_models import Agent, Conversation, Tool
from app.repositories.tenant_repository import RepositoryFactory
from app.services.agent_orchestrator import (
    AgentOrchestrator,
    PlanParseError,
    PlanStep,
    TaskPlan,
    build_fallback_plan,
    parse_plan,
)

CONV_PREFIX = "/api/v1/conversations"
AUTH_PREFIX = "/api/v1/auth"


def _run(coro):
    """Run a coroutine to completion (no pytest-asyncio dependency)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session():
    from app.core.database import get_sessionmaker as SessionLocal

    db = SessionLocal()()
    try:
        yield db
    finally:
        db.close()


def _register(client, suffix="orch"):
    email = f"{suffix}-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Orch Owner",
            "organization_name": f"Orch Org {uuid.uuid4()}",
            "organization_slug": f"{suffix}-org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_agent(public_id, name="Agent", org_id=None, model_name="anthropic/claude-3.5-sonnet"):
    """Build an in-memory Agent model (no DB session needed for mechanics tests)."""
    agent = Agent(
        organization_id=str(org_id or uuid.uuid4()),
        data={
            "name": name,
            "system_prompt": f"You are {name}.",
            "public_id": public_id,
            "model_name": model_name,
        },
    )
    agent.id = uuid.uuid4()
    return agent


def _insert_tool(db, org_id, name, config=None, input_schema=None):
    tool = Tool(
        organization_id=str(org_id),
        data={
            "name": name,
            "tool_type": "function",
            "description": f"{name} description",
            "config": config or {"function_name": "echo"},
            "input_schema": input_schema or {"type": "object", "properties": {"value": {"type": "string"}}},
        },
    )
    tool.id = uuid.uuid4()
    return RepositoryFactory(db, org_id).tools().create(tool)


def _create_agent(db_session, org_id, public_id="orch-agent"):
    agent = Agent(
        organization_id=org_id,
        data={
            "name": "Orch Agent",
            "system_prompt": "You are a helpful assistant.",
            "public_id": public_id,
        },
    )
    agent.id = uuid.uuid4()
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


def _create_conversation(client, token, agent_id):
    resp = client.post(
        f"{CONV_PREFIX}/",
        json={"agent_id": str(agent_id), "session_id": f"session-{uuid.uuid4()}"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Fake LLM provider (OpenAI-compatible, injectable)
# ---------------------------------------------------------------------------


class _FakeProvider:
    """Routes by prompt content: planning / synthesis / step echo.

    ``plan_json`` is returned when the prompt asks to decompose a goal. For
    normal steps it echoes the full user prompt so downstream steps can prove
    they received the upstream output. Tracks in-flight calls to demonstrate
    parallel vs sequential execution.
    """

    inflight = {"n": 0, "max": 0}

    def __init__(self, api_key="", base_url="", default_headers=None, plan_json=None):
        self.api_key = api_key
        self.base_url = base_url
        self._plan_json = plan_json

    async def generate(self, request):
        _FakeProvider.inflight["n"] += 1
        _FakeProvider.inflight["max"] = max(
            _FakeProvider.inflight["max"], _FakeProvider.inflight["n"]
        )
        await asyncio.sleep(0.02)
        _FakeProvider.inflight["n"] -= 1

        text = request.messages[-1].content if request.messages else ""
        if self._plan_json is not None and "DECOMPOSE THE GOAL" in text:
            return GenerationResponse(content=json.dumps(self._plan_json))
        if text.startswith("Goal:"):
            return GenerationResponse(content="SYNTHESIZED: " + text[:40])
        # Step: echo the full user prompt so context hand-off is observable.
        return GenerationResponse(content=text)

    async def stream(self, request):
        yield StreamChunk(delta_content="x")

    async def close(self):
        return None

    def supports_tools(self):
        return True


class _FlakyProvider(_FakeProvider):
    """Like _FakeProvider but raises when the step instruction contains BOOM,

    so one step can be forced to fail while others succeed (recovery testing).
    """

    async def generate(self, request):
        text = request.messages[-1].content if request.messages else ""
        if "BOOM" in text:
            raise RuntimeError("injected step failure")
        return await super().generate(request)


class _FakeFunctionCallingProvider:
    """Provider stub for the function-calling reuse integration test.

    Emits a single tool_call on the tools request, then streams a final answer
    that echoes the injected tool output (mirrors
    ``test_function_calling._FakeOpenRouterProvider``).
    """

    def __init__(self, api_key="", base_url="", default_headers=None):
        self.api_key = api_key
        self.base_url = base_url

    async def generate(self, request):
        if getattr(request, "tools", None):
            name = request.tools[0]["function"]["name"]
            return GenerationResponse(
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps({"value": "hello-world"}),
                        },
                    }
                ],
            )
        return GenerationResponse(content="", tool_calls=[])

    async def stream(self, request):
        yield StreamChunk(delta_content="The tool returned: hello-world.")

    async def close(self):
        return None


# ---------------------------------------------------------------------------
# Plan parsing / validation
# ---------------------------------------------------------------------------


def test_parse_plan_valid():
    plan = parse_plan(
        {
            "goal": "ship feature",
            "steps": [
                {"step_id": "1", "agent": "a1", "instruction": "design"},
                {"step_id": "2", "agent": "a2", "instruction": "build", "depends_on": ["1"]},
            ],
        }
    )
    assert plan.goal == "ship feature"
    assert [s.step_id for s in plan.steps] == ["1", "2"]
    assert plan.steps[1].depends_on == ["1"]
    assert plan.roots()[0].step_id == "1"


def test_parse_plan_strips_code_fence():
    raw = '```json\n{"steps": [{"step_id": "1", "agent": "a1", "instruction": "x"}]}\n```'
    plan = parse_plan(raw)
    assert plan.steps[0].agent_ref == "a1"


def test_parse_plan_requires_steps():
    with pytest.raises(PlanParseError):
        parse_plan({"goal": "g"})
    with pytest.raises(PlanParseError):
        parse_plan({"steps": []})
    with pytest.raises(PlanParseError):
        parse_plan("not json")


def test_parse_plan_rejects_unknown_dependency():
    with pytest.raises(PlanParseError):
        parse_plan(
            {
                "steps": [
                    {"step_id": "1", "agent": "a1", "instruction": "x", "depends_on": ["9"]}
                ]
            }
        )


def test_parse_plan_rejects_duplicate_step_id():
    with pytest.raises(PlanParseError):
        parse_plan(
            {
                "steps": [
                    {"step_id": "1", "agent": "a1", "instruction": "x"},
                    {"step_id": "1", "agent": "a2", "instruction": "y"},
                ]
            }
        )


def test_parse_plan_rejects_missing_agent():
    with pytest.raises(PlanParseError):
        parse_plan({"steps": [{"step_id": "1", "instruction": "x"}]})


def test_build_fallback_plan_single_step():
    agent = _make_agent("fb1", name="Lead")
    plan = build_fallback_plan("do the thing", agent)
    assert len(plan.steps) == 1
    assert plan.steps[0].agent_ref == "fb1"
    assert plan.steps[0].instruction == "do the thing"


# ---------------------------------------------------------------------------
# Task Planning (LLM planner mocked)
# ---------------------------------------------------------------------------


def test_plan_task_uses_llm_planner(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_orchestrator.rag_llm_enabled", lambda: True
    )
    a1 = _make_agent("p-a1")
    a2 = _make_agent("p-a2")
    plan_json = {
        "goal": "launch",
        "steps": [
            {"step_id": "1", "agent": "p-a1", "instruction": "research"},
            {"step_id": "2", "agent": "p-a2", "instruction": "write", "depends_on": ["1"]},
        ],
    }

    class _Planner(_FakeProvider):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._plan_json = plan_json

    monkeypatch.setattr(
        "app.services.agent_orchestrator.OpenRouterProvider", _Planner
    )
    orch = AgentOrchestrator(uuid.uuid4(), db=None, agents=[a1, a2])
    plan = _run(orch.plan_task("launch", [a1, a2]))
    assert [s.agent_ref for s in plan.steps] == ["p-a1", "p-a2"]
    assert plan.steps[1].depends_on == ["1"]


def test_plan_task_falls_back_offline(monkeypatch):
    # No LLM configured -> deterministic single-step fallback.
    monkeypatch.setattr(
        "app.services.agent_orchestrator.rag_llm_enabled", lambda: False
    )
    a1 = _make_agent("fb-a1")
    orch = AgentOrchestrator(uuid.uuid4(), db=None, agents=[a1])
    plan = _run(orch.plan_task("goal", [a1]))
    assert len(plan.steps) == 1
    assert plan.steps[0].agent_ref == "fb-a1"


# ---------------------------------------------------------------------------
# Sequential & Parallel Execution
# ---------------------------------------------------------------------------


def test_parallel_execution_runs_concurrently(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_orchestrator.OpenRouterProvider", _FakeProvider
    )
    _FakeProvider.inflight = {"n": 0, "max": 0}
    a1 = _make_agent("par-a1")
    a2 = _make_agent("par-a2")
    orch = AgentOrchestrator(uuid.uuid4(), db=None, agents=[a1, a2], max_retries=0)
    plan = TaskPlan(
        goal="g",
        steps=[
            PlanStep(step_id="1", agent_ref="par-a1", instruction="left"),
            PlanStep(step_id="2", agent_ref="par-a2", instruction="right"),
        ],
    )
    result = _run(orch.execute_plan(plan, "g", max_retries=0))
    assert [r.status for r in result.step_results] == ["success", "success"]
    # Both steps were in-flight at the same time -> max concurrency >= 2.
    assert _FakeProvider.inflight["max"] >= 2


def test_sequential_execution_respects_dependency(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_orchestrator.OpenRouterProvider", _FakeProvider
    )
    _FakeProvider.inflight = {"n": 0, "max": 0}
    a1 = _make_agent("seq-a1")
    a2 = _make_agent("seq-a2")
    orch = AgentOrchestrator(uuid.uuid4(), db=None, agents=[a1, a2], max_retries=0)
    plan = TaskPlan(
        goal="g",
        steps=[
            PlanStep(step_id="1", agent_ref="seq-a1", instruction="first"),
            PlanStep(step_id="2", agent_ref="seq-a2", instruction="second", depends_on=["1"]),
        ],
    )
    result = _run(orch.execute_plan(plan, "g", max_retries=0))
    assert _FakeProvider.inflight["max"] == 1  # never two in flight
    # The dependent step ran after the first (ordered results).
    assert [r.step_id for r in result.step_results] == ["1", "2"]


# ---------------------------------------------------------------------------
# Agent-to-Agent Communication
# ---------------------------------------------------------------------------


def test_agent_to_agent_context_handoff(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_orchestrator.OpenRouterProvider", _FakeProvider
    )
    a1 = _make_agent("com-a1")
    a2 = _make_agent("com-a2")
    orch = AgentOrchestrator(uuid.uuid4(), db=None, agents=[a1, a2], max_retries=0)
    plan = TaskPlan(
        goal="goal-X",
        steps=[
            PlanStep(step_id="1", agent_ref="com-a1", instruction="produce RESULT-A"),
            PlanStep(step_id="2", agent_ref="com-a2", instruction="consume", depends_on=["1"]),
        ],
    )
    result = _run(orch.execute_plan(plan, "goal-X", max_retries=0))
    out1 = result.step_results[0].output
    out2 = result.step_results[1].output
    # Step 2's prompt (and therefore its echoed output) must contain step 1's
    # output -- the agent-to-agent hand-off.
    assert out1 in out2


def test_failed_upstream_passes_error_context(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_orchestrator.OpenRouterProvider", _FlakyProvider
    )
    a1 = _make_agent("err-a1")
    a2 = _make_agent("err-a2")
    orch = AgentOrchestrator(uuid.uuid4(), db=None, agents=[a1, a2], max_retries=0)
    plan = TaskPlan(
        goal="g",
        steps=[
            PlanStep(step_id="1", agent_ref="err-a1", instruction="BOOM fail me"),
            PlanStep(step_id="2", agent_ref="err-a2", instruction="recover", depends_on=["1"]),
        ],
    )
    result = _run(orch.execute_plan(plan, "g", max_retries=0))
    assert result.step_results[0].status == "failed"
    # Downstream still ran (continue_on_failure) and received the error context.
    assert result.step_results[1].status == "success"
    assert "FAILED" in result.step_results[1].output
    assert result.status == "completed_with_errors"


# ---------------------------------------------------------------------------
# Failure Recovery (retry + halt)
# ---------------------------------------------------------------------------


def test_failure_recovery_retries_then_marks_failed(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_orchestrator.OpenRouterProvider", _FlakyProvider
    )
    a1 = _make_agent("rec-a1")
    orch = AgentOrchestrator(uuid.uuid4(), db=None, agents=[a1], max_retries=1)
    plan = TaskPlan(
        goal="g",
        steps=[PlanStep(step_id="1", agent_ref="rec-a1", instruction="BOOM always")],
    )
    result = _run(orch.execute_plan(plan, "g", max_retries=1))
    failed = result.step_results[0]
    assert failed.status == "failed"
    assert failed.error_type == "execution_error"
    # 1 initial try + 1 retry == 2 attempts.
    assert failed.attempts == 2
    assert result.status == "completed_with_errors"


def test_halt_on_failure_skips_downstream(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_orchestrator.OpenRouterProvider", _FlakyProvider
    )
    a1 = _make_agent("halt-a1")
    a2 = _make_agent("halt-a2")
    orch = AgentOrchestrator(uuid.uuid4(), db=None, agents=[a1, a2], max_retries=0)
    plan = TaskPlan(
        goal="g",
        steps=[
            PlanStep(step_id="1", agent_ref="halt-a1", instruction="BOOM"),
            PlanStep(step_id="2", agent_ref="halt-a2", instruction="skip me", depends_on=["1"]),
        ],
    )
    result = _run(orch.execute_plan(plan, "g", halt_on_failure=True, max_retries=0))
    statuses = {r.step_id: r.status for r in result.step_results}
    assert statuses["1"] == "failed"
    assert statuses["2"] == "skipped"
    assert result.step_results[1].error_type == "halted"


def test_unreachable_dependency_is_skipped(monkeypatch):
    # Step depends on a non-existent step -> unreachable; the executor must not
    # loop forever and must mark it skipped.
    monkeypatch.setattr(
        "app.services.agent_orchestrator.OpenRouterProvider", _FakeProvider
    )
    a1 = _make_agent("cyc-a1")
    orch = AgentOrchestrator(uuid.uuid4(), db=None, agents=[a1], max_retries=0)
    plan = TaskPlan(
        goal="g",
        steps=[PlanStep(step_id="1", agent_ref="cyc-a1", instruction="x", depends_on=["99"])],
    )
    result = _run(orch.execute_plan(plan, "g", max_retries=0))
    assert result.step_results[0].status == "skipped"
    assert result.step_results[0].error_type == "unreachable"


# ---------------------------------------------------------------------------
# Agent resolution / tenant isolation (service level)
# ---------------------------------------------------------------------------


def test_step_with_unknown_agent_fails_not_found(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_orchestrator.OpenRouterProvider", _FakeProvider
    )
    a1 = _make_agent("real-a1")
    orch = AgentOrchestrator(uuid.uuid4(), db=None, agents=[a1], max_retries=0)
    plan = TaskPlan(
        goal="g",
        steps=[PlanStep(step_id="1", agent_ref="ghost-agent", instruction="x")],
    )
    result = _run(orch.execute_plan(plan, "g", max_retries=0))
    failed = result.step_results[0]
    assert failed.status == "failed"
    assert failed.error_type == "agent_not_found"
    assert "not found in this tenant" in (failed.error or "")


def test_agent_resolved_only_within_tenant(monkeypatch):
    # Org A's agent must not resolve inside Org B's orchestrator, even with the
    # same public_id reference (resolution is performed on the tenant's agents).
    monkeypatch.setattr(
        "app.services.agent_orchestrator.OpenRouterProvider", _FakeProvider
    )
    org_a_agent = _make_agent("shared-pid", org_id=uuid.uuid4())
    # Org B's orchestrator is built with NO agents (it cannot see Org A's).
    orch_b = AgentOrchestrator(uuid.uuid4(), db=None, agents=[], max_retries=0)
    plan = TaskPlan(
        goal="g",
        steps=[PlanStep(step_id="1", agent_ref="shared-pid", instruction="x")],
    )
    # Sanity: Org A can resolve it.
    orch_a = AgentOrchestrator(uuid.uuid4(), db=None, agents=[org_a_agent], max_retries=0)
    res_a = _run(
        orch_a.execute_plan(
            TaskPlan(
                goal="g",
                steps=[PlanStep(step_id="1", agent_ref="shared-pid", instruction="x")],
            ),
            "g",
            max_retries=0,
        )
    )
    assert res_a.step_results[0].status == "success"
    # Org B cannot -> agent_not_found (tenant isolation at agent resolution).
    res_b = _run(orch_b.execute_plan(plan, "g", max_retries=0))
    assert res_b.step_results[0].status == "failed"
    assert res_b.step_results[0].error_type == "agent_not_found"


# ---------------------------------------------------------------------------
# Function-calling reuse within a step (DB-backed integration)
# ---------------------------------------------------------------------------


def test_orchestrator_step_reuses_function_calling(db_session, client, monkeypatch):
    import app.services.function_calling as fc_mod
    import app.services.agent_orchestrator as ao_mod

    # Turn the LLM path on for function-calling, but keep orchestrator planning
    # offline (so we get the deterministic single-step fallback plan).
    monkeypatch.setattr(fc_mod, "rag_llm_enabled", lambda: True)
    monkeypatch.setattr(fc_mod, "OpenRouterProvider", _FakeFunctionCallingProvider)
    monkeypatch.setattr(ao_mod, "OpenRouterProvider", _FakeFunctionCallingProvider)

    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    _insert_tool(db_session, org_id, name=f"echo-{uuid.uuid4()}")

    orch = AgentOrchestrator(org_id, db_session)
    result = _run(orch.orchestrate("run the echo tool"))
    assert result.status in ("completed", "completed_with_errors")
    step = result.step_results[0]
    # The step ran through run_function_calling -> tool executed in-tenant.
    assert step.tool_calls, "expected tool calls from function-calling reuse"
    assert step.tool_results, "expected tool results from function-calling reuse"
    assert any(
        "hello-world" in json.dumps(r.get("output", "")) for r in step.tool_results
    )


# ---------------------------------------------------------------------------
# HTTP integration: orchestrate endpoint + tenant isolation
# ---------------------------------------------------------------------------


def test_orchestrate_endpoint_streams_and_persists(client, db_session, monkeypatch):
    import app.services.agent_orchestrator as ao_mod

    monkeypatch.setattr(ao_mod, "OpenRouterProvider", _FakeProvider)
    token, org_id = _register(client, suffix="http")
    agent = _create_agent(db_session, org_id, public_id="http-agent")
    conv_id = _create_conversation(client, token, agent.id)

    resp = client.post(
        f"{CONV_PREFIX}/{conv_id}/orchestrate",
        json={"goal": "write a report"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    types = [e["type"] for e in events]
    assert "plan" in types
    assert "step_result" in types
    assert "token" in types
    assert events[-1]["type"] == "done"
    assert events[-1]["data"]["status"] in ("completed", "completed_with_errors")

    # Messages persisted: user goal + step assistant + final assistant.
    msgs = client.get(
        f"{CONV_PREFIX}/{conv_id}/messages", headers=_auth_headers(token)
    ).json()
    roles = [m["role"] for m in msgs]
    assert "user" in roles
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    # One assistant message per executed step + one for the final answer.
    assert len(assistant_msgs) >= 2, "expected step + final assistant messages"
    # The step output echoes the user prompt (which embeds the goal), proving a
    # step message was persisted for this tenant's agent.
    assert any("Overall goal: write a report" in m["content"] for m in assistant_msgs)

    # Cleanup.
    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete(
        synchronize_session=False
    )
    db_session.query(Agent).filter(Agent.id == str(agent.id)).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_orchestrate_endpoint_tenant_isolation(client, db_session, monkeypatch):
    import app.services.agent_orchestrator as ao_mod

    monkeypatch.setattr(ao_mod, "OpenRouterProvider", _FakeProvider)

    # Org A owns the conversation; Org B must not be able to orchestrate it.
    token_a, org_a = _register(client, suffix="iso-a")
    agent_a = _create_agent(db_session, org_a, public_id="iso-a-agent")
    conv_a = _create_conversation(client, token_a, agent_a.id)

    token_b, org_b = _register(client, suffix="iso-b")

    resp = client.post(
        f"{CONV_PREFIX}/{conv_a}/orchestrate",
        json={"goal": "poke"},
        headers=_auth_headers(token_b),
    )
    # Conversation belongs to Org A; Org B resolves nothing -> 404.
    assert resp.status_code == 404, resp.text

    db_session.query(Conversation).filter(Conversation.id == str(conv_a)).delete(
        synchronize_session=False
    )
    db_session.query(Agent).filter(Agent.id == str(agent_a.id)).delete(
        synchronize_session=False
    )
    db_session.commit()
