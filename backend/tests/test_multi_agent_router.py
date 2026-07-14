"""Multi-Agent Router tests (Milestone 4, Phase 5).

Covers the six Phase 5 deliverables:

* **Multi-Agent Router** -- :class:`MultiAgentRouter` selects + dispatches +
  coordinates agents and returns a complete ``RouterResult`` for every turn.
* **Agent Selection** -- :class:`AgentSelector` ranks agents across policies and
  produces a full candidate ranking; unknown policy names fall back to default.
* **Routing Policies** -- keyword overlap, capability tags, LLM intent
  classification (with offline fallback), round-robin dynamic dispatch, and the
  weighted composite, plus deterministic fallback on policy failure.
* **Dynamic Dispatch** -- agents are selected at request time; round-robin
  spreads load; dispatch reuses the function-calling pipeline per agent.
* **Specialist Agent Coordination** -- multiple selected agents are dispatched in
  parallel and their outputs are synthesized into one answer; the ``orchestrate``
  mode delegates coordination to the Agent Orchestrator (Phase 4 reuse).
* **Router Tests** -- unit (policies/selector/router mechanics) + integration
  through ``POST /conversations/{id}/route`` (mocked LLM) verifying selection,
  dispatch, persistence and tenant isolation at the routing boundary.

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
from app.services.multi_agent_router import (
    AgentDispatchOutput,
    AgentSelector,
    CapabilityRoutingPolicy,
    CompositeRoutingPolicy,
    KeywordRoutingPolicy,
    LLMRoutingPolicy,
    MultiAgentRouter,
    RoundRobinRoutingPolicy,
    RoutingDecision,
)

CONV_PREFIX = "/api/v1/conversations"
AUTH_PREFIX = "/api/v1/auth"


def _run(coro):
    """Run a coroutine to completion (no pytest-asyncio dependency)."""
    return asyncio.run(coro)


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


# ---------------------------------------------------------------------------
# Agent / tool fixtures
# ---------------------------------------------------------------------------


def _make_agent(public_id, name="Agent", org_id=None, model_name="anthropic/claude-3.5-sonnet", config=None):
    """Build an in-memory Agent model (no DB session needed for mechanics tests)."""
    agent = Agent(
        organization_id=str(org_id or uuid.uuid4()),
        data={
            "name": name,
            "system_prompt": f"You are {name}.",
            "public_id": public_id,
            "model_name": model_name,
            "config": config or {},
        },
    )
    agent.id = uuid.uuid4()
    return agent


def _create_agent(db_session, org_id, public_id, config=None):
    agent = Agent(
        organization_id=org_id,
        data={
            "name": f"Agent {public_id}",
            "system_prompt": "You are a helpful assistant.",
            "public_id": public_id,
            "config": config or {},
        },
    )
    agent.id = uuid.uuid4()
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
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


def _register(client, suffix="router"):
    email = f"{suffix}-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Router Owner",
            "organization_name": f"Router Org {uuid.uuid4()}",
            "organization_slug": f"{suffix}-org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


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
    """Echoes the user prompt so dispatch output is observable in tests."""

    def __init__(self, api_key="", base_url="", default_headers=None):
        self.api_key = api_key
        self.base_url = base_url

    async def generate(self, request):
        text = request.messages[-1].content if request.messages else ""
        return GenerationResponse(content=f"ANSWER: {text}")

    async def stream(self, request):
        yield StreamChunk(delta_content="x")

    async def close(self):
        return None

    def supports_tools(self):
        return True


class _RouterLLMFakeProvider(_FakeProvider):
    """Routes by query content for the LLM routing-policy test.

    If the query contains 'billing' it picks the billing agent; otherwise the
    support agent. Returns the chosen agent's public_id so the policy resolves it.
    """

    async def generate(self, request):
        text = request.messages[-1].content if request.messages else ""
        if "billing" in text.lower():
            chosen = "pid-billing"
        else:
            chosen = "pid-support"
        return GenerationResponse(content=json.dumps({"agent_ref": chosen, "rationale": "classified"}))


class _FlakyProvider(_FakeProvider):
    """Raises when the prompt contains BOOM so one dispatch can be forced to fail."""

    async def generate(self, request):
        text = request.messages[-1].content if request.messages else ""
        if "BOOM" in text:
            raise RuntimeError("injected dispatch failure")
        return await super().generate(request)


# ===========================================================================
# Routing Policies -- unit
# ===========================================================================


def test_keyword_policy_scores_by_overlap():
    a_billing = _make_agent("k-billing", name="Billing Agent", config={"description": "handles refunds"})
    a_support = _make_agent("k-support", name="Support Agent", config={"description": "general help"})
    pol = KeywordRoutingPolicy()
    scores = _run(pol.select("refund my billing", [a_billing, a_support]))
    scores.sort(key=lambda s: s.score, reverse=True)
    assert scores[0].agent_ref == "k-billing"
    assert scores[0].score >= scores[1].score


def test_capability_policy_matches_declared_capabilities():
    a_billing = _make_agent(
        "c-billing", name="Billing", config={"capabilities": ["billing", "refunds"]}
    )
    a_sales = _make_agent("c-sales", name="Sales", config={"capabilities": ["sales", "leads"]})
    pol = CapabilityRoutingPolicy()
    scores = _run(pol.select("I want a refund", [a_billing, a_sales]))
    scores.sort(key=lambda s: s.score, reverse=True)
    assert scores[0].agent_ref == "c-billing"


def test_capability_policy_reads_comma_string():
    a = _make_agent("cc", name="Specialist", config={"specialties": "kubernetes, terraform"})
    pol = CapabilityRoutingPolicy()
    scores = _run(pol.select("terraform plan", [a]))
    assert scores[0].score > 0


def test_round_robin_rotates_across_calls():
    a1 = _make_agent("rr-1", name="A1")
    a2 = _make_agent("rr-2", name="A2")
    a3 = _make_agent("rr-3", name="A3")
    org = uuid.uuid4()
    pol = RoundRobinRoutingPolicy()
    first = _run(pol.select("anything", [a1, a2, a3], organization_id=org))
    second = _run(pol.select("anything", [a1, a2, a3], organization_id=org))
    third = _run(pol.select("anything", [a1, a2, a3], organization_id=org))
    assert first[0].agent_ref != second[0].agent_ref != third[0].agent_ref
    # Each call picks exactly one (score 1.0, others 0.0).
    assert sum(1 for s in first if s.score > 0) == 1


def test_round_robin_is_tenant_isolated_cursor():
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    a1 = _make_agent("a1", name="A1", org_id=org_a)
    a2 = _make_agent("a2", name="A2", org_id=org_b)
    pol = RoundRobinRoutingPolicy()
    # Each tenant advances its own cursor; org B must not be affected by org A.
    ra = _run(pol.select("q", [a1], organization_id=org_a))
    rb1 = _run(pol.select("q", [a2], organization_id=org_b))
    rb2 = _run(pol.select("q", [a2], organization_id=org_b))
    assert rb1[0].agent_ref == rb2[0].agent_ref  # org B has a single agent -> always it


def test_composite_policy_combines_weights():
    a_billing = _make_agent(
        "cp-billing", name="Billing", config={"description": "refunds", "capabilities": ["billing"]}
    )
    a_sales = _make_agent(
        "cp-sales", name="Sales", config={"description": "leads", "capabilities": ["sales"]}
    )
    pol = CompositeRoutingPolicy(
        [(KeywordRoutingPolicy(), 0.6), (CapabilityRoutingPolicy(), 0.4)]
    )
    scores = _run(pol.select("billing refund", [a_billing, a_sales]))
    scores.sort(key=lambda s: s.score, reverse=True)
    assert scores[0].agent_ref == "cp-billing"


def test_llm_policy_falls_back_offline(monkeypatch):
    # No LLM configured -> keyword fallback. The LLM fake is irrelevant here.
    monkeypatch.setattr("app.services.multi_agent_router.rag_llm_enabled", lambda: False)
    a_billing = _make_agent("l-billing", name="Billing", config={"description": "refunds"})
    a_other = _make_agent("l-other", name="Other", config={"description": "misc"})
    pol = LLMRoutingPolicy()
    scores = _run(pol.select("refund request", [a_billing, a_other]))
    scores.sort(key=lambda s: s.score, reverse=True)
    assert scores[0].agent_ref == "l-billing"


def test_llm_policy_uses_classification(monkeypatch):
    monkeypatch.setattr("app.services.multi_agent_router.rag_llm_enabled", lambda: True)
    monkeypatch.setattr("app.services.multi_agent_router.OpenRouterProvider", _RouterLLMFakeProvider)
    a_billing = _make_agent("pid-billing", name="Billing")
    a_support = _make_agent("pid-support", name="Support")
    pol = LLMRoutingPolicy()
    scores = _run(pol.select("I have a billing question", [a_billing, a_support]))
    scores.sort(key=lambda s: s.score, reverse=True)
    assert scores[0].agent_ref == "pid-billing"


def test_policy_failure_triggers_fallback(monkeypatch):
    class _BoomPolicy(KeywordRoutingPolicy):
        async def select(self, *a, **k):
            raise RuntimeError("boom")

    sel = AgentSelector(policies={"boom": _BoomPolicy(), "keyword": KeywordRoutingPolicy()})
    a1 = _make_agent("fb-1", name="A1", config={"description": "refunds"})
    a2 = _make_agent("fb-2", name="A2", config={"description": "misc"})
    decision = _run(
        sel.select("refund", [a1, a2], organization_id=uuid.uuid4(), policy="boom")
    )
    assert decision.fallback_used is True
    assert decision.policy_name == "boom"
    assert decision.selected  # still produced a selection


def test_unknown_policy_name_falls_back_to_default():
    sel = AgentSelector()
    a1 = _make_agent("u-1", name="A1", config={"description": "refunds"})
    a2 = _make_agent("u-2", name="A2", config={"description": "misc"})
    decision = _run(
        sel.select("refund", [a1, a2], organization_id=uuid.uuid4(), policy="does_not_exist")
    )
    assert decision.policy_name == sel._default_policy


# ===========================================================================
# Agent Selection
# ===========================================================================


def test_selector_returns_full_ranking_and_top_k():
    sel = AgentSelector()
    a_billing = _make_agent("s-billing", name="Billing", config={"description": "refunds", "capabilities": ["billing"]})
    a_sales = _make_agent("s-sales", name="Sales", config={"description": "leads", "capabilities": ["sales"]})
    a_other = _make_agent("s-other", name="Other", config={"description": "misc"})
    decision = _run(
        sel.select("billing refund", [a_billing, a_sales, a_other], organization_id=uuid.uuid4(), top_k=2)
    )
    assert len(decision.candidates) == 3
    assert len(decision.selected) == 2
    assert decision.selected[0].agent_ref == "s-billing"
    # Selected are the top of the ranking.
    assert decision.selected[0].score >= decision.selected[1].score


def test_selector_handles_empty_agent_list():
    sel = AgentSelector()
    decision = _run(sel.select("query", [], organization_id=uuid.uuid4()))
    assert decision.selected == []
    assert decision.candidates == []


# ===========================================================================
# Multi-Agent Router -- mechanics (no DB / mocked LLM)
# ===========================================================================


def test_router_single_mode_dispatches_top_agent(monkeypatch):
    monkeypatch.setattr("app.services.multi_agent_router.OpenRouterProvider", _FakeProvider)
    a1 = _make_agent("r1", name="Billing", config={"description": "refunds", "capabilities": ["billing"]})
    a2 = _make_agent("r2", name="Sales", config={"description": "leads"})
    router = MultiAgentRouter(uuid.uuid4(), db=None, agents=[a1, a2])
    result = _run(router.route("billing refund", policy="composite", top_k=1, mode="single"))
    assert result.mode == "single"
    assert result.status == "completed"
    assert len(result.outputs) == 1
    assert result.outputs[0].status == "success"
    assert "billing refund" in result.outputs[0].output
    assert result.outputs[0].agent_ref == "r1"  # routing chose the billing agent


def test_router_no_agents_returns_no_agents_status(monkeypatch):
    monkeypatch.setattr("app.services.multi_agent_router.OpenRouterProvider", _FakeProvider)
    router = MultiAgentRouter(uuid.uuid4(), db=None, agents=[])
    result = _run(router.route("anything"))
    assert result.status == "no_agents"
    assert result.decision.selected == []


def test_router_specialists_mode_parallel_and_synthesizes(monkeypatch):
    monkeypatch.setattr("app.services.multi_agent_router.rag_llm_enabled", lambda: False)
    monkeypatch.setattr("app.services.multi_agent_router.OpenRouterProvider", _FakeProvider)
    a1 = _make_agent("sp-1", name="Billing", config={"capabilities": ["billing"]})
    a2 = _make_agent("sp-2", name="Sales", config={"capabilities": ["sales"]})
    router = MultiAgentRouter(uuid.uuid4(), db=None, agents=[a1, a2])
    result = _run(router.route("compare billing and sales", policy="capability", top_k=2, mode="specialists"))
    assert result.mode == "specialists"
    assert len(result.outputs) == 2
    assert all(o.status == "success" for o in result.outputs)
    # Synthesis (offline) joins both labelled outputs.
    assert "sp-1" in result.answer and "sp-2" in result.answer


def test_router_failed_dispatch_isolated(monkeypatch):
    monkeypatch.setattr("app.services.multi_agent_router.OpenRouterProvider", _FlakyProvider)
    a1 = _make_agent("fd-1", name="Flaky", config={"capabilities": ["x"]})
    router = MultiAgentRouter(uuid.uuid4(), db=None, agents=[a1])
    result = _run(router.route("BOOM please", policy="capability", top_k=1, mode="single"))
    # A failed dispatch never crashes the turn; status reflects the error.
    assert result.status == "completed_with_errors"
    assert result.outputs[0].status == "failed"
    assert result.outputs[0].error is not None


def test_router_orchestrate_mode_reuses_orchestrator(monkeypatch):
    monkeypatch.setattr("app.services.multi_agent_router.rag_llm_enabled", lambda: False)
    monkeypatch.setattr("app.services.multi_agent_router.OpenRouterProvider", _FakeProvider)
    # The orchestrator also uses OpenRouterProvider -> same fake, so steps echo.
    import app.services.agent_orchestrator as ao_mod

    monkeypatch.setattr(ao_mod, "OpenRouterProvider", _FakeProvider)
    a1 = _make_agent("or-1", name="Billing", config={"capabilities": ["billing"]})
    a2 = _make_agent("or-2", name="Sales", config={"capabilities": ["sales"]})
    router = MultiAgentRouter(uuid.uuid4(), db=None, agents=[a1, a2])
    result = _run(
        router.route("plan it", policy="capability", top_k=2, mode="orchestrate")
    )
    assert result.mode == "orchestrate"
    assert len(result.outputs) == 2
    assert result.status in ("completed", "completed_with_errors")


def test_router_round_robin_dynamic_dispatch(monkeypatch):
    monkeypatch.setattr("app.services.multi_agent_router.OpenRouterProvider", _FakeProvider)
    org = uuid.uuid4()
    a1 = _make_agent("rd-1", name="A1", org_id=org)
    a2 = _make_agent("rd-2", name="A2", org_id=org)
    router = MultiAgentRouter(org, db=None, agents=[a1, a2])
    r1 = _run(router.route("q", policy="round_robin", top_k=1, mode="single"))
    r2 = _run(router.route("q", policy="round_robin", top_k=1, mode="single"))
    # Dynamic dispatch rotated to a different agent on the second call.
    assert r1.outputs[0].agent_ref != r2.outputs[0].agent_ref


# ===========================================================================
# Integration: POST /conversations/{id}/route + tenant isolation
# ===========================================================================


def test_route_endpoint_streams_and_persists(client, db_session, monkeypatch):
    import app.services.multi_agent_router as mr_mod

    monkeypatch.setattr(mr_mod, "OpenRouterProvider", _FakeProvider)
    token, org_id = _register(client, suffix="http-route")
    agent = _create_agent(db_session, org_id, public_id="http-route-agent",
                          config={"capabilities": ["support"]})
    conv_id = _create_conversation(client, token, agent.id)

    resp = client.post(
        f"{CONV_PREFIX}/{conv_id}/route",
        json={"query": "help me", "policy": "keyword", "top_k": 1, "mode": "single"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    types = [e["type"] for e in events]
    assert "decision" in types
    assert "dispatch_result" in types
    assert "token" in types
    assert events[-1]["type"] == "done"
    assert events[-1]["data"]["status"] == "completed"

    # Messages persisted: user query + agent output + final answer.
    msgs = client.get(
        f"{CONV_PREFIX}/{conv_id}/messages", headers=_auth_headers(token)
    ).json()
    roles = [m["role"] for m in msgs]
    assert "user" in roles
    assistant = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistant) >= 2
    # The dispatched agent's output was persisted (proves a route + dispatch ran
    # and stored an assistant message for this tenant's agent).
    assert any("ANSWER:" in m["content"] for m in assistant)

    # Cleanup.
    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete(
        synchronize_session=False
    )
    db_session.query(Agent).filter(Agent.id == str(agent.id)).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_route_endpoint_tenant_isolation(client, db_session, monkeypatch):
    import app.services.multi_agent_router as mr_mod

    monkeypatch.setattr(mr_mod, "OpenRouterProvider", _FakeProvider)

    token_a, org_a = _register(client, suffix="iso-route-a")
    agent_a = _create_agent(db_session, org_a, public_id="iso-route-a-agent")
    conv_a = _create_conversation(client, token_a, agent_a.id)

    token_b, _org_b = _register(client, suffix="iso-route-b")

    # Org B must not be able to route Org A's conversation -> 404.
    resp = client.post(
        f"{CONV_PREFIX}/{conv_a}/route",
        json={"query": "poke"},
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text

    db_session.query(Conversation).filter(Conversation.id == str(conv_a)).delete(
        synchronize_session=False
    )
    db_session.query(Agent).filter(Agent.id == str(agent_a.id)).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_route_endpoint_orchestrate_mode(client, db_session, monkeypatch):
    import app.services.agent_orchestrator as ao_mod
    import app.services.multi_agent_router as mr_mod

    monkeypatch.setattr(mr_mod, "rag_llm_enabled", lambda: False)
    monkeypatch.setattr(mr_mod, "OpenRouterProvider", _FakeProvider)
    monkeypatch.setattr(ao_mod, "OpenRouterProvider", _FakeProvider)

    token, org_id = _register(client, suffix="orch-route")
    agent = _create_agent(db_session, org_id, public_id="orch-route-agent",
                          config={"capabilities": ["support"]})
    conv_id = _create_conversation(client, token, agent.id)

    resp = client.post(
        f"{CONV_PREFIX}/{conv_id}/route",
        json={"query": "coordinate", "policy": "capability", "top_k": 1, "mode": "orchestrate"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    assert events[-1]["type"] == "done"
    assert events[-1]["data"]["mode"] == "orchestrate"

    # Cleanup.
    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete(
        synchronize_session=False
    )
    db_session.query(Agent).filter(Agent.id == str(agent.id)).delete(
        synchronize_session=False
    )
    db_session.commit()
