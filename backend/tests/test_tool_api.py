"""Tool Registry API tests (Milestone 4, Phase 1).

Mirrors the style of ``test_knowledge_base_api.py`` / ``test_agent_api.py``:
register a real user (yielding a JWT + organization), then exercise the tool
endpoints with a ``Bearer`` token. Tenant isolation is enforced at the API
boundary -- ``organization_id`` is derived from the authenticated principal,
never from request data.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.all_models import Tool

API_PREFIX = "/api/v1/tools"
AUTH_PREFIX = "/api/v1/auth"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session():
    """Create a database session for test setup/teardown."""
    from app.core.database import get_sessionmaker as SessionLocal

    db = SessionLocal()()
    try:
        yield db
    finally:
        db.close()


def _register(client: TestClient):
    """Register a user and return (access_token, organization_id)."""
    email = f"tool-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Tool Owner",
            "organization_name": f"Tool Org {uuid.uuid4()}",
            "organization_slug": f"tool-org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_org(client, db_session):
    """Register an owner and yield (token, organization_id); clean up on exit."""
    token, org_id = _register(client)
    yield token, org_id

    # Cleanup: tools created via the API for this org.
    db_session.query(Tool).filter(Tool.organization_id == org_id).delete(
        synchronize_session=False
    )
    db_session.commit()


def _create_tool(client, token, **overrides):
    """Register a tool via the API and return its parsed JSON body."""
    payload = {
        "name": f"tool-{uuid.uuid4()}",
        "tool_type": "function",
        "description": "A test tool",
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
    }
    payload.update(overrides)
    resp = client.post(f"{API_PREFIX}/", json=payload, headers=_auth_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# POST /tools  (Registration)
# ---------------------------------------------------------------------------


def test_register_requires_authentication(client):
    response = client.post(f"{API_PREFIX}/", json={"name": "x", "tool_type": "function"})
    assert response.status_code == 401


def test_register_returns_201(client, auth_org):
    token, org_id = auth_org
    body = _create_tool(client, token, display_name="My Tool")

    assert body["name"].startswith("tool-")
    assert body["display_name"] == "My Tool"
    assert body["organization_id"] == org_id
    assert body["tool_type"] == "function"
    # Server-side defaults.
    assert body["is_active"] is True
    assert body["description"] == "A test tool"
    assert body["input_schema"] == {
        "type": "object",
        "properties": {"q": {"type": "string"}},
    }
    assert "id" in body
    assert "created_at" in body


def test_register_applies_custom_fields(client, auth_org):
    token, org_id = auth_org
    body = _create_tool(
        client,
        token,
        is_active=False,
        config={"endpoint": "https://example.com"},
        display_name="Custom",
    )
    assert body["is_active"] is False
    assert body["config"] == {"endpoint": "https://example.com"}
    assert body["display_name"] == "Custom"


def test_register_invalid_tool_type_422(client, auth_org):
    token, org_id = auth_org
    response = client.post(
        f"{API_PREFIX}/",
        json={"name": "bad", "tool_type": "rocket"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


def test_register_invalid_input_schema_shape_422(client, auth_org):
    token, org_id = auth_org
    response = client.post(
        f"{API_PREFIX}/",
        json={
            "name": "bad",
            "tool_type": "function",
            "input_schema": {"type": "string"},
        },
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


def test_register_input_schema_not_object_422(client, auth_org):
    token, org_id = auth_org
    response = client.post(
        f"{API_PREFIX}/",
        json={"name": "bad", "tool_type": "function", "input_schema": "nope"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


def test_register_missing_name_422(client, auth_org):
    token, org_id = auth_org
    response = client.post(
        f"{API_PREFIX}/", json={"tool_type": "function"}, headers=_auth_headers(token)
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /tools  (Discovery)
# ---------------------------------------------------------------------------


def test_list_includes_created(client, auth_org):
    token, org_id = auth_org
    created = _create_tool(client, token)
    created_id = created["id"]

    response = client.get(f"{API_PREFIX}/", headers=_auth_headers(token))
    assert response.status_code == 200
    ids = {t["id"] for t in response.json()}
    assert created_id in ids


def test_list_filter_by_type(client, auth_org):
    token, org_id = auth_org
    fn = _create_tool(client, token, tool_type="function", name=f"fn-{uuid.uuid4()}")
    _create_tool(client, token, tool_type="webhook", name=f"wh-{uuid.uuid4()}")

    response = client.get(
        f"{API_PREFIX}/", params={"tool_type": "webhook"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == _id_of(body, f"wh-")
    assert fn["id"] not in {t["id"] for t in body}


def test_list_filter_by_active(client, auth_org):
    token, org_id = auth_org
    _create_tool(client, token, is_active=False, name=f"off-{uuid.uuid4()}")
    on = _create_tool(client, token, is_active=True, name=f"on-{uuid.uuid4()}")

    response = client.get(
        f"{API_PREFIX}/", params={"is_active": True}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    ids = {t["id"] for t in response.json()}
    assert on["id"] in ids
    assert _id_of(response.json(), "off-") is None


def test_list_search(client, auth_org):
    token, org_id = auth_org
    _create_tool(client, token, name="alpha-scanner", display_name="Alpha Scanner")
    _create_tool(client, token, name="beta-widget", display_name="Beta Widget")

    response = client.get(
        f"{API_PREFIX}/", params={"search": "alpha"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "alpha-scanner"


def test_list_types_returns_supported(client, auth_org):
    token, org_id = auth_org
    response = client.get(f"{API_PREFIX}/types", headers=_auth_headers(token))
    assert response.status_code == 200
    assert set(response.json()) == {
        "webhook",
        "function",
        "lead_capture",
        "human_escalation",
        "custom",
    }


def test_list_requires_authentication(client, auth_org):
    response = client.get(f"{API_PREFIX}/")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /tools/{id}
# ---------------------------------------------------------------------------


def test_get_returns_200(client, auth_org):
    token, org_id = auth_org
    created = _create_tool(client, token)
    response = client.get(
        f"{API_PREFIX}/{created['id']}", headers=_auth_headers(token)
    )
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_invalid_id_400(client, auth_org):
    token, org_id = auth_org
    response = client.get(f"{API_PREFIX}/not-a-uuid", headers=_auth_headers(token))
    assert response.status_code == 400


def test_get_unknown_404(client, auth_org):
    token, org_id = auth_org
    response = client.get(f"{API_PREFIX}/{uuid.uuid4()}", headers=_auth_headers(token))
    assert response.status_code == 404


def test_get_requires_authentication(client, auth_org):
    token, org_id = auth_org
    created = _create_tool(client, token)
    response = client.get(f"{API_PREFIX}/{created['id']}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# PUT /tools/{id}
# ---------------------------------------------------------------------------


def test_update_returns_200(client, auth_org):
    token, org_id = auth_org
    created = _create_tool(client, token)
    response = client.put(
        f"{API_PREFIX}/{created['id']}",
        json={"description": "Updated description", "display_name": "Renamed"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "Updated description"
    assert body["display_name"] == "Renamed"
    # Untouched fields retain their values.
    assert body["tool_type"] == "function"


def test_update_deactivate(client, auth_org):
    token, org_id = auth_org
    created = _create_tool(client, token)
    response = client.put(
        f"{API_PREFIX}/{created['id']}",
        json={"is_active": False},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_update_unknown_404(client, auth_org):
    token, org_id = auth_org
    response = client.put(
        f"{API_PREFIX}/{uuid.uuid4()}",
        json={"description": "x"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 404


def test_update_invalid_tool_type_422(client, auth_org):
    token, org_id = auth_org
    created = _create_tool(client, token)
    response = client.put(
        f"{API_PREFIX}/{created['id']}",
        json={"tool_type": "rocket"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /tools/{id}
# ---------------------------------------------------------------------------


def test_delete_returns_204(client, auth_org):
    token, org_id = auth_org
    created = _create_tool(client, token)
    response = client.delete(
        f"{API_PREFIX}/{created['id']}", headers=_auth_headers(token)
    )
    assert response.status_code == 204

    follow_up = client.get(
        f"{API_PREFIX}/{created['id']}", headers=_auth_headers(token)
    )
    assert follow_up.status_code == 404


def test_delete_unknown_404(client, auth_org):
    token, org_id = auth_org
    response = client.delete(
        f"{API_PREFIX}/{uuid.uuid4()}", headers=_auth_headers(token)
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_tool_not_visible_across_tenants(client, db_session):
    # Org A registers a tool; Org B must not see it.
    token_a, org_a = _register(client)
    tool_a = _create_tool(client, token_a)
    token_b, org_b = _register(client)

    # Org B's list must not contain Org A's tool.
    list_b = client.get(f"{API_PREFIX}/", headers=_auth_headers(token_b))
    assert list_b.status_code == 200
    assert tool_a["id"] not in {t["id"] for t in list_b.json()}

    # Org B cannot fetch Org A's tool by id (tenant filter -> 404).
    get_b = client.get(
        f"{API_PREFIX}/{tool_a['id']}", headers=_auth_headers(token_b)
    )
    assert get_b.status_code == 404

    # Cleanup Org A's tool.
    db_session.query(Tool).filter(Tool.organization_id == org_a).delete(
        synchronize_session=False
    )
    db_session.commit()


def _id_of(items, prefix: str):
    for item in items:
        if item["name"].startswith(prefix):
            return item["id"]
    return None
