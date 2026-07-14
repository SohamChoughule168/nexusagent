"""Conversation API tests (Milestone 3).

Every conversation endpoint is now protected: ``organization_id`` is derived
from the authenticated principal via ``app.core.auth_dependencies`` rather than
accepted from the request. These tests register a real user (which yields a
valid JWT + organization), create an agent in that organization, and exercise
the conversation endpoints with a ``Bearer`` token.

Style mirrors ``test_tenant_isolation.py`` / ``test_milestone1.py``: real
database session fixture, ``TestClient(app)`` from ``app.main``, and
organization/agent created per-test for FK integrity.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.all_models import Agent, Conversation, Message

API_PREFIX = "/api/v1/conversations"
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
    email = f"owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Owner",
            "organization_name": f"Org {uuid.uuid4()}",
            "organization_slug": f"org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_org_agent(client, db_session):
    """Register an owner, create a real agent in their org for FK integrity."""
    token, org_id = _register(client)

    agent = Agent(
        organization_id=org_id,
        data={
            "name": "Test Agent",
            "system_prompt": "You are a test agent.",
            "public_id": f"test-agent-{uuid.uuid4()}",
        },
    )
    # The Agent model overrides the base `id` without a server_default, so an
    # explicit id is required for an ORM insert (the API never inserts agents,
    # it only reads them via the repository, so this does not affect endpoints).
    agent.id = uuid.uuid4()
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)

    yield token, org_id, str(agent.id)

    # Cleanup: conversations/messages created via the API first, then fixtures.
    db_session.query(Message).filter(Message.organization_id == org_id).delete(
        synchronize_session=False
    )
    db_session.query(Conversation).filter(
        Conversation.organization_id == org_id
    ).delete(synchronize_session=False)
    db_session.delete(agent)
    db_session.commit()


# ---------------------------------------------------------------------------
# POST /conversations
# ---------------------------------------------------------------------------


def test_create_conversation_requires_authentication(client):
    payload = {"agent_id": str(uuid.uuid4()), "session_id": f"session-{uuid.uuid4()}"}
    # No bearer token -> 401.
    response = client.post(f"{API_PREFIX}/", json=payload)
    assert response.status_code == 401


def test_create_conversation_returns_201(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    payload = {
        "agent_id": agent_id,
        "session_id": f"session-{uuid.uuid4()}",
        "user_identifier": "tester@example.com",
        "status": "active",
    }
    response = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == 201

    body = response.json()
    assert body["organization_id"] == org_id
    assert body["agent_id"] == agent_id
    assert body["session_id"] == payload["session_id"]
    assert body["status"] == "active"
    assert "id" in body


def test_create_conversation_defaults_status(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    payload = {
        "agent_id": agent_id,
        "session_id": f"session-{uuid.uuid4()}",
    }
    response = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == 201
    assert response.json()["status"] == "active"


def test_create_conversation_validation_error_missing_session(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    # session_id is required on ConversationCreate.
    response = client.post(
        f"{API_PREFIX}/", json={"agent_id": agent_id}, headers=_auth_headers(token)
    )
    assert response.status_code == 422


def test_create_conversation_invalid_agent_id(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    payload = {
        "agent_id": "not-a-uuid",
        "session_id": f"session-{uuid.uuid4()}",
    }
    response = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == 400


def test_create_conversation_unknown_agent_404(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    payload = {
        "agent_id": str(uuid.uuid4()),
        "session_id": f"session-{uuid.uuid4()}",
    }
    response = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /conversations
# ---------------------------------------------------------------------------


def test_list_conversations_empty(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    response = client.get(f"{API_PREFIX}/", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json() == []


def test_list_conversations_returns_created(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    payload = {
        "agent_id": agent_id,
        "session_id": f"session-{uuid.uuid4()}",
    }
    create = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert create.status_code == 201

    response = client.get(f"{API_PREFIX}/", headers=_auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == create.json()["id"]


# ---------------------------------------------------------------------------
# POST /conversations/{id}/messages
# ---------------------------------------------------------------------------


def _create_conversation(client, token, agent_id):
    payload = {
        "agent_id": agent_id,
        "session_id": f"session-{uuid.uuid4()}",
    }
    response = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_create_message_returns_201(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    conversation_id = _create_conversation(client, token, agent_id)

    payload = {"role": "user", "content": "Hello there"}
    response = client.post(
        f"{API_PREFIX}/{conversation_id}/messages",
        json=payload,
        headers=_auth_headers(token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["conversation_id"] == conversation_id
    assert body["organization_id"] == org_id
    assert body["role"] == "user"
    assert body["content"] == "Hello there"
    assert "id" in body


def test_create_message_invalid_conversation_id(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    payload = {"role": "user", "content": "Hello"}
    # Invalid path UUID -> 422 (FastAPI validation).
    response = client.post(
        f"{API_PREFIX}/not-a-uuid/messages",
        json=payload,
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


def test_create_message_unknown_conversation_404(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    payload = {"role": "user", "content": "Hello"}
    response = client.post(
        f"{API_PREFIX}/{uuid.uuid4()}/messages",
        json=payload,
        headers=_auth_headers(token),
    )
    assert response.status_code == 404


def test_create_message_requires_authentication(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    conversation_id = _create_conversation(client, token, agent_id)
    payload = {"role": "user", "content": "Hello"}
    # No token -> 401 even though the conversation exists.
    response = client.post(
        f"{API_PREFIX}/{conversation_id}/messages", json=payload
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /conversations/{id}/messages
# ---------------------------------------------------------------------------


def test_list_messages_empty(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    conversation_id = _create_conversation(client, token, agent_id)

    response = client.get(
        f"{API_PREFIX}/{conversation_id}/messages", headers=_auth_headers(token)
    )
    assert response.status_code == 200
    assert response.json() == []


def test_list_messages_returns_created(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    conversation_id = _create_conversation(client, token, agent_id)

    payload = {"role": "assistant", "content": "Hi! How can I help?"}
    created = client.post(
        f"{API_PREFIX}/{conversation_id}/messages",
        json=payload,
        headers=_auth_headers(token),
    )
    assert created.status_code == 201

    response = client.get(
        f"{API_PREFIX}/{conversation_id}/messages", headers=_auth_headers(token)
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["content"] == "Hi! How can I help?"
    assert body[0]["role"] == "assistant"


def test_list_messages_invalid_conversation_id(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    # Invalid path UUID -> 422 (FastAPI validation).
    response = client.get(
        f"{API_PREFIX}/not-a-uuid/messages", headers=_auth_headers(token)
    )
    assert response.status_code == 422


def test_list_messages_unknown_conversation_404(client, auth_org_agent):
    token, org_id, agent_id = auth_org_agent
    response = client.get(
        f"{API_PREFIX}/{uuid.uuid4()}/messages", headers=_auth_headers(token)
    )
    assert response.status_code == 404
