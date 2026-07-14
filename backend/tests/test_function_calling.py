"""Function Calling service tests (Milestone 4, Phase 3).

Covers the four deliverables of the function-calling service:

* Function Schema Generation (OpenAI-compatible tool schemas)
* Automatic Tool Selection
* Tool Argument Validation
* Tool execution + Tool Result Injection inside the tenant

Plus an end-to-end integration test through ``POST /conversations/{id}/chat``
with the LLM provider mocked, exercising the full
discover -> schema -> LLM tool_call -> execute -> inject -> persist flow and
verifying tenant isolation at the execution boundary.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.ai.providers.base import GenerationResponse, StreamChunk
from app.main import app
from app.models.all_models import Agent, Conversation, Tool
from app.repositories.tenant_repository import RepositoryFactory
from app.services.function_calling import (
    auto_select_tools,
    discover_tools,
    execute_tool_call,
    function_calling_enabled,
    generate_function_schema,
    generate_function_schemas,
    parse_tool_call,
    validate_tool_arguments,
)

CONV_PREFIX = "/api/v1/conversations"
TOOL_PREFIX = "/api/v1/tools"
AUTH_PREFIX = "/api/v1/auth"


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


def _register(client: TestClient):
    email = f"fc-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "FC Owner",
            "organization_name": f"FC Org {uuid.uuid4()}",
            "organization_slug": f"fc-org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_tool(
    name="t",
    tool_type="function",
    description="A tool",
    display_name=None,
    config=None,
    input_schema=None,
):
    """Build an in-memory Tool model (no DB session needed for schema/parse)."""
    tool = Tool(
        organization_id=uuid.uuid4(),
        data={
            "name": name,
            "tool_type": tool_type,
            "description": description,
            "display_name": display_name,
            "config": config or {},
            "input_schema": input_schema or {},
        },
    )
    tool.id = uuid.uuid4()
    return tool


def _insert_tool(db, org_id, name, tool_type="function", config=None, input_schema=None):
    """Insert a real tool row into ``org_id`` and return the ORM Tool."""
    tool = Tool(
        organization_id=str(org_id),
        data={
            "name": name,
            "tool_type": tool_type,
            "description": f"{name} description",
            "config": config or {},
            "input_schema": input_schema or {},
        },
    )
    tool.id = uuid.uuid4()
    return RepositoryFactory(db, org_id).tools().create(tool)


def _create_agent(db_session, org_id):
    agent = Agent(
        organization_id=org_id,
        data={
            "name": "FC Agent",
            "system_prompt": "You are a helpful assistant.",
            "public_id": f"fc-agent-{uuid.uuid4()}",
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
# Function Schema Generation (OpenAI-compatible)
# ---------------------------------------------------------------------------


def test_generate_function_schema_openai_shape():
    tool = _make_tool(
        name="weather_lookup",
        description="Fetches current weather for a city.",
        input_schema={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )
    schema = generate_function_schema(tool)
    assert schema == {
        "type": "function",
        "function": {
            "name": "weather_lookup",
            "description": "Fetches current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }


def test_generate_function_schema_parameters_is_input_schema():
    tool = _make_tool(input_schema={"type": "object", "properties": {"q": {"type": "string"}}})
    schema = generate_function_schema(tool)
    # The registered tool's input_schema is passed through verbatim as parameters.
    assert schema["function"]["parameters"] == tool.input_schema


def test_generate_function_schema_empty_schema_defaults_to_object():
    tool = _make_tool(input_schema={})
    schema = generate_function_schema(tool)
    assert schema["function"]["parameters"] == {"type": "object", "properties": {}}


def test_generate_function_schema_description_falls_back_to_name():
    tool = _make_tool(name="echo_tool", description="", display_name="")
    schema = generate_function_schema(tool)
    assert schema["function"]["description"] == "echo_tool"


def test_generate_function_schema_description_falls_back_to_display_name():
    tool = _make_tool(name="x", description="", display_name="Echo Display")
    schema = generate_function_schema(tool)
    assert schema["function"]["description"] == "Echo Display"


def test_generate_function_schemas_batch():
    tools = [
        _make_tool(name="a", input_schema={"type": "object", "properties": {}}),
        _make_tool(name="b", input_schema={"type": "object", "properties": {}}),
    ]
    schemas = generate_function_schemas(tools)
    assert [s["function"]["name"] for s in schemas] == ["a", "b"]
    assert all(s["type"] == "function" for s in schemas)


# ---------------------------------------------------------------------------
# Automatic Tool Selection
# ---------------------------------------------------------------------------


def test_auto_select_tools_empty_tools_returns_empty():
    assert auto_select_tools("anything", []) == []


def test_auto_select_tools_empty_query_returns_all():
    tools = [_make_tool(name="a"), _make_tool(name="b"), _make_tool(name="c")]
    assert auto_select_tools("", tools) == tools


def test_auto_select_tools_keyword_overlap_selects_subset():
    weather = _make_tool(name="weather_lookup", description="current weather")
    refund = _make_tool(name="refund_request", description="issue a refund")
    other = _make_tool(name="ticket_create", description="create a ticket")
    selected = auto_select_tools("what is the weather today?", [weather, refund, other])
    assert selected == [weather]


def test_auto_select_tools_no_overlap_returns_all():
    weather = _make_tool(name="weather_lookup", description="current weather")
    refund = _make_tool(name="refund_request", description="issue a refund")
    # Query shares no tokens with either tool description/name.
    selected = auto_select_tools("zzz qqq xyz", [weather, refund])
    assert set(selected) == {weather, refund}


def test_auto_select_tools_respects_max_tools():
    tools = [_make_tool(name=f"t{i}") for i in range(5)]
    selected = auto_select_tools("", tools, max_tools=2)
    assert len(selected) == 2


# ---------------------------------------------------------------------------
# Tool Argument Validation (reuses engine validator)
# ---------------------------------------------------------------------------


def test_validate_tool_arguments_valid():
    tool = _make_tool(
        input_schema={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        }
    )
    assert validate_tool_arguments(tool, {"city": "Paris"}) == []


def test_validate_tool_arguments_missing_required():
    tool = _make_tool(
        input_schema={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        }
    )
    errors = validate_tool_arguments(tool, {})
    assert any("missing required argument: city" in e for e in errors)


def test_validate_tool_arguments_wrong_type():
    tool = _make_tool(input_schema={"type": "object", "properties": {"n": {"type": "integer"}}})
    errors = validate_tool_arguments(tool, {"n": "not-a-number"})
    assert any("must be integer" in e for e in errors)


# ---------------------------------------------------------------------------
# Tool-call parsing (OpenAI wire format)
# ---------------------------------------------------------------------------


def test_parse_tool_call_json_string():
    call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "weather_lookup", "arguments": '{"city": "Paris"}'},
    }
    name, args, err = parse_tool_call(call)
    assert name == "weather_lookup"
    assert args == {"city": "Paris"}
    assert err is None


def test_parse_tool_call_already_dict():
    call = {"function": {"name": "echo", "arguments": {"value": "hi"}}}
    name, args, err = parse_tool_call(call)
    assert args == {"value": "hi"}
    assert err is None


def test_parse_tool_call_none_arguments():
    call = {"function": {"name": "echo", "arguments": None}}
    name, args, err = parse_tool_call(call)
    assert args == {}
    assert err is None


def test_parse_tool_call_invalid_json_error():
    call = {"function": {"name": "echo", "arguments": "{not valid json"}}
    name, args, err = parse_tool_call(call)
    assert err is not None
    assert "invalid JSON" in err
    assert args == {}


# ---------------------------------------------------------------------------
# Tenant-scoped tool resolution + execution
# ---------------------------------------------------------------------------


def test_execute_tool_call_runs_builtin_function(db_session, client):
    _, org_id = _register(client)
    _insert_tool(
        db_session,
        org_id,
        name="echo_t",
        config={"function_name": "echo"},
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
    )
    call = {"id": "call_1", "function": {"name": "echo_t", "arguments": json.dumps({"value": "hi"})}}
    tool, result = execute_tool_call(call, org_id, db_session)
    assert tool is not None
    assert result.success is True
    assert result.output == "hi"
    assert result.error_type is None


def test_execute_tool_call_unknown_tool_not_found(db_session, client):
    _, org_id = _register(client)
    call = {"id": "c", "function": {"name": "ghost_tool", "arguments": "{}"}}
    tool, result = execute_tool_call(call, org_id, db_session)
    assert tool is None
    assert result.success is False
    assert result.error_type == "not_found"


def test_execute_tool_call_argument_validation_error(db_session, client):
    _, org_id = _register(client)
    _insert_tool(
        db_session,
        org_id,
        name="needs_city",
        config={"function_name": "echo"},
        input_schema={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )
    call = {"id": "c", "function": {"name": "needs_city", "arguments": "{}"}}
    tool, result = execute_tool_call(call, org_id, db_session)
    assert tool is not None
    assert result.success is False
    assert result.error_type == "argument_validation"


def test_execute_tool_call_invalid_json_is_error(db_session, client):
    _, org_id = _register(client)
    _insert_tool(db_session, org_id, name="echo_t", config={"function_name": "echo"})
    call = {"id": "c", "function": {"name": "echo_t", "arguments": "{bad"}}
    tool, result = execute_tool_call(call, org_id, db_session)
    # A parse failure surfaces before tool resolution, so no Tool is returned
    # and the call becomes a controlled argument_validation error result.
    assert tool is None
    assert result.success is False
    assert result.error_type == "argument_validation"


def test_execute_tool_call_tenant_isolation(db_session, client):
    # Tool belongs to org A; executing a call attributed to org B must NOT run
    # the tool (it is not found within org B).
    _, org_a = _register(client)
    _, org_b = _register(client)
    _insert_tool(
        db_session,
        org_a,
        name="secret_t",
        config={"function_name": "echo"},
    )
    call = {"id": "c", "function": {"name": "secret_t", "arguments": json.dumps({"value": "x"})}}
    tool, result = execute_tool_call(call, org_b, db_session)
    assert tool is None
    assert result.success is False
    assert result.error_type == "not_found"


def test_discover_tools_respects_tenant(db_session, client):
    _, org_a = _register(client)
    _, org_b = _register(client)
    _insert_tool(db_session, org_a, name="a_only")
    # Org B has no tools.
    assert discover_tools(org_b, db_session) == []


def test_discover_tools_returns_active_only(db_session, client):
    _, org = _register(client)
    _insert_tool(db_session, org, name="active_t")
    # An inactive tool is excluded from discovery.
    inactive = _insert_tool(db_session, org, name="inactive_t")
    inactive.is_active = False
    RepositoryFactory(db_session, org).tools().update(inactive)

    names = {t.name for t in discover_tools(org, db_session)}
    assert "active_t" in names
    assert "inactive_t" not in names


def test_discover_tools_agent_enabled_allowlist(db_session, client):
    _, org = _register(client)
    allowed = _insert_tool(db_session, org, name="allowed_t")
    _insert_tool(db_session, org, name="other_t")

    class _Agent:
        config = {"enabled_tool_ids": [str(allowed.id)]}

    discovered = discover_tools(org, db_session, agent=_Agent())
    assert [t.name for t in discovered] == ["allowed_t"]


# ---------------------------------------------------------------------------
# function_calling_enabled gate
# ---------------------------------------------------------------------------


def test_function_calling_enabled_false_without_llm(db_session, client, monkeypatch):
    _, org = _register(client)
    _insert_tool(db_session, org, name="t")

    # Force rag_llm_enabled to False so the gate is closed even with tools.
    import app.services.function_calling as fc_mod

    monkeypatch.setattr(fc_mod, "rag_llm_enabled", lambda: False)
    assert function_calling_enabled(org, db_session) is False


def test_function_calling_enabled_true_with_llm_and_tools(db_session, client, monkeypatch):
    _, org = _register(client)
    _insert_tool(db_session, org, name="t")

    import app.services.function_calling as fc_mod

    monkeypatch.setattr(fc_mod, "rag_llm_enabled", lambda: True)
    assert function_calling_enabled(org, db_session) is True


def test_function_calling_enabled_false_without_tools(db_session, client, monkeypatch):
    _, org = _register(client)
    import app.services.function_calling as fc_mod

    monkeypatch.setattr(fc_mod, "rag_llm_enabled", lambda: True)
    assert function_calling_enabled(org, db_session) is False


# ---------------------------------------------------------------------------
# Integration: chat endpoint runs the full function-calling loop (mocked LLM)
# ---------------------------------------------------------------------------


class _FakeOpenRouterProvider:
    """OpenAI-compatible provider stub: emits a tool_call on the first (tools)
    request, then streams a final answer that echoes the injected tool output.
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
        # The augmented messages carry the injected tool result; surface it.
        yield StreamChunk(delta_content="The tool returned: hello-world.")

    async def close(self):
        return None


def test_chat_function_calling_executes_and_injects_results(client, db_session, monkeypatch):
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)

    # Register an active function (echo) tool in the tenant.
    tool = _insert_tool(
        db_session,
        org_id,
        name=f"echo-{uuid.uuid4()}",
        config={"function_name": "echo"},
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
    )

    # Force the LLM path on (no real key in tests) and substitute the provider.
    import app.services.function_calling as fc_mod
    import app.services.rag as rag_mod

    monkeypatch.setattr(rag_mod, "rag_llm_enabled", lambda: True)
    monkeypatch.setattr(fc_mod, "rag_llm_enabled", lambda: True)
    monkeypatch.setattr(fc_mod, "OpenRouterProvider", _FakeOpenRouterProvider)

    conv_id = _create_conversation(client, token, agent.id)
    resp = client.post(
        f"{CONV_PREFIX}/{conv_id}/chat",
        json={"message": "call the echo tool please"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    answer = resp.text
    # The final streamed answer should contain the injected tool output.
    assert "hello-world" in answer

    # The assistant message persists the executed tool calls + results.
    msgs = client.get(
        f"{CONV_PREFIX}/{conv_id}/messages", headers=_auth_headers(token)
    ).json()
    assistant = next(m for m in msgs if m["role"] == "assistant")
    assert assistant["tool_calls"]
    assert assistant["tool_calls"]["calls"]
    assert assistant["tool_results"]["results"]
    result0 = assistant["tool_results"]["results"][0]
    assert result0["success"] is True
    assert "hello-world" in json.dumps(result0["output"])
    # The assistant content itself was persisted from the streamed answer.
    assert "hello-world" in assistant["content"]

    # Cleanup.
    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete(
        synchronize_session=False
    )
    db_session.query(Tool).filter(Tool.organization_id == str(org_id)).delete(
        synchronize_session=False
    )
    db_session.query(Agent).filter(Agent.id == str(agent.id)).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_chat_offline_with_tool_present_still_works(client, db_session, monkeypatch):
    # When no LLM is configured, registering a tool must NOT change the offline
    # RAG behaviour -- the turn still returns a 200 answer.
    import app.services.function_calling as fc_mod
    import app.services.rag as rag_mod

    monkeypatch.setattr(rag_mod, "rag_llm_enabled", lambda: False)
    monkeypatch.setattr(fc_mod, "rag_llm_enabled", lambda: False)

    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    _insert_tool(db_session, org_id, name=f"echo-{uuid.uuid4()}", config={"function_name": "echo"})

    conv_id = _create_conversation(client, token, agent.id)
    resp = client.post(
        f"{CONV_PREFIX}/{conv_id}/chat",
        json={"message": "hello"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text

    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete(
        synchronize_session=False
    )
    db_session.query(Tool).filter(Tool.organization_id == str(org_id)).delete(
        synchronize_session=False
    )
    db_session.query(Agent).filter(Agent.id == str(agent.id)).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_chat_function_calling_respects_tenant_isolation(client, db_session, monkeypatch):
    # Org A owns a tool; Org B's chat must not execute it (no tool calls made,
    # because Org B has no tools to offer the LLM).
    import app.services.function_calling as fc_mod
    import app.services.rag as rag_mod

    monkeypatch.setattr(rag_mod, "rag_llm_enabled", lambda: True)
    monkeypatch.setattr(fc_mod, "rag_llm_enabled", lambda: True)
    monkeypatch.setattr(fc_mod, "OpenRouterProvider", _FakeOpenRouterProvider)

    token_a, org_a = _register(client)
    agent_a = _create_agent(db_session, org_a)
    _insert_tool(db_session, org_a, name=f"echo-{uuid.uuid4()}", config={"function_name": "echo"})

    token_b, org_b = _register(client)
    agent_b = _create_agent(db_session, org_b)

    conv_a = _create_conversation(client, token_a, agent_a.id)
    conv_b = _create_conversation(client, token_b, agent_b.id)

    resp_b = client.post(
        f"{CONV_PREFIX}/{conv_b}/chat",
        json={"message": "use the tool"},
        headers=_auth_headers(token_b),
    )
    assert resp_b.status_code == 200, resp_b.text

    msgs_b = client.get(
        f"{CONV_PREFIX}/{conv_b}/messages", headers=_auth_headers(token_b)
    ).json()
    assistant_b = next(m for m in msgs_b if m["role"] == "assistant")
    # Org B has no tools, so no tool calls were made / executed.
    assert not assistant_b.get("tool_calls") or not assistant_b["tool_calls"].get("calls")

    for cid in (conv_a, conv_b):
        db_session.query(Conversation).filter(Conversation.id == str(cid)).delete(
            synchronize_session=False
        )
    for oid in (org_a, org_b):
        db_session.query(Tool).filter(Tool.organization_id == str(oid)).delete(
            synchronize_session=False
        )
    for aid in (agent_a.id, agent_b.id):
        db_session.query(Agent).filter(Agent.id == str(aid)).delete(
            synchronize_session=False
        )
    db_session.commit()
