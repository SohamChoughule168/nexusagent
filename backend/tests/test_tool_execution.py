"""Tool Execution endpoint tests (Milestone 4, Phase 2).

Exercises ``POST /api/v1/tools/{tool_id}/execute`` end-to-end against a real
database: register a tenant, create tools via the registry API, then run them
through the execution engine. Tenant isolation is asserted both directions --
Org B cannot execute Org A's tool (404, not a 200 error result).
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

API_PREFIX = "/api/v1/tools"
AUTH_PREFIX = "/api/v1/auth"


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
    email = f"exec-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Exec Owner",
            "organization_name": f"Exec Org {uuid.uuid4()}",
            "organization_slug": f"exec-org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_org(client, db_session):
    token, org_id = _register(client)
    yield token, org_id
    # No tool rows are persisted by execution (the engine is side-effect free
    # for function/lead_capture/human_escalation), so nothing to clean up here.


def _create_tool(client, token, **overrides):
    payload = {
        "name": f"tool-{uuid.uuid4()}",
        "tool_type": "function",
        "input_schema": {"type": "object", "properties": {"value": {"type": "string"}}},
    }
    payload.update(overrides)
    resp = client.post(f"{API_PREFIX}/", json=payload, headers=_auth_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _execute(client, token, tool_id, arguments=None):
    return client.post(
        f"{API_PREFIX}/{tool_id}/execute",
        json={"arguments": arguments or {}},
        headers=_auth_headers(token),
    )


# ---------------------------------------------------------------------------
# Auth / not-found
# ---------------------------------------------------------------------------


def test_execute_requires_authentication(client):
    response = client.post(f"{API_PREFIX}/{uuid.uuid4()}/execute", json={})
    assert response.status_code == 401


def test_execute_unknown_tool_404(client, auth_org):
    token, _ = auth_org
    response = _execute(client, token, uuid.uuid4())
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Strategies via the endpoint
# ---------------------------------------------------------------------------


def test_execute_function_success(client, auth_org):
    token, _ = auth_org
    tool = _create_tool(client, token, config={"function_name": "echo"})
    response = _execute(client, token, tool["id"], {"value": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["output"] == "hello"
    assert body["tool_type"] == "function"
    assert body["tool_id"] == tool["id"]
    assert body["execution_id"]
    assert body["duration_ms"] >= 0
    assert "started_at" in body


def test_execute_function_add(client, auth_org):
    token, _ = auth_org
    tool = _create_tool(client, token, config={"function_name": "add"})
    response = _execute(client, token, tool["id"], {"a": 4, "b": 6})
    assert response.status_code == 200
    assert response.json()["output"] == 10.0


def test_execute_function_argument_validation_failure(client, auth_org):
    token, _ = auth_org
    tool = _create_tool(client, token, config={"function_name": "echo"})
    response = _execute(client, token, tool["id"], {"value": 123})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error_type"] == "argument_validation"


def test_execute_lead_capture_via_endpoint(client, auth_org):
    token, _ = auth_org
    tool = _create_tool(client, token, tool_type="lead_capture")
    response = _execute(
        client, token, tool["id"],
        {"name": "Jane", "email": "jane@example.com"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["output"]["name"] == "Jane"
    assert body["output"]["email"] == "jane@example.com"
    assert body["tool_type"] == "lead_capture"


def test_execute_human_escalation_via_endpoint(client, auth_org):
    token, _ = auth_org
    tool = _create_tool(
        client, token, tool_type="human_escalation",
        input_schema={"type": "object", "properties": {"reason": {"type": "string"}}},
    )
    response = _execute(
        client, token, tool["id"], {"reason": "billing dispute"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["output"]["escalated"] is True
    assert body["output"]["reason"] == "billing dispute"
    assert body["tool_type"] == "human_escalation"


def test_execute_custom_is_not_runnable(client, auth_org):
    token, _ = auth_org
    tool = _create_tool(client, token, tool_type="custom")
    response = _execute(client, token, tool["id"], {})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error_type"] == "tool_error"


def test_execute_webhook_success(client, auth_org, monkeypatch):
    from unittest.mock import MagicMock

    resp = MagicMock()
    resp.json.return_value = {"forecast": "sunny"}
    resp.text = ""
    resp.status_code = 200
    client_mock = MagicMock()
    client_mock.__enter__.return_value.request.return_value = resp
    monkeypatch.setattr(
        "app.services.tool_executor.httpx.Client", lambda *a, **k: client_mock
    )

    token, _ = auth_org
    tool = _create_tool(
        client, token, tool_type="webhook",
        config={"endpoint": "https://api.example.com/weather"},
    )
    response = _execute(client, token, tool["id"], {"city": "Berlin"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["output"] == {"forecast": "sunny"}
    assert body["meta"]["http_status"] == 200


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_cannot_execute_another_tenants_tool(client):
    token_a, _ = _register(client)
    tool_a = _create_tool(client, token_a, config={"function_name": "echo"})
    token_b, _ = _register(client)

    # Org B executing Org A's tool must 404 (tenant filter), never 200.
    response = _execute(client, token_b, tool_a["id"], {"value": "x"})
    assert response.status_code == 404


def test_isolation_full_roundtrip(client):
    token_a, _ = _register(client)
    tool_a = _create_tool(client, token_a, config={"function_name": "echo"})
    token_b, _ = _register(client)
    tool_b = _create_tool(client, token_b, config={"function_name": "echo"})

    # Each tenant can run only its own tool.
    ra = _execute(client, token_a, tool_a["id"], {"value": "a"})
    rb = _execute(client, token_b, tool_b["id"], {"value": "b"})
    assert ra.status_code == 200 and ra.json()["output"] == "a"
    assert rb.status_code == 200 and rb.json()["output"] == "b"

    # Cross-tenant execution is blocked.
    assert _execute(client, token_a, tool_b["id"], {"value": "x"}).status_code == 404
    assert _execute(client, token_b, tool_a["id"], {"value": "x"}).status_code == 404
