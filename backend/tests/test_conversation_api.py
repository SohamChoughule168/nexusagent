"""Conversation API tests (Milestone 3).

Style mirrors the existing ``test_tenant_isolation.py`` / ``test_milestone1.py``:
real database session fixture, ``TestClient(app)`` from ``app.main``, and
organization/agent created per-test for FK integrity.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from app.models.organization import Organization
from app.models.all_models import (
    Agent,
    Conversation,
    Message,
    OrganizationMember,
)

API_PREFIX = "/api/v1/conversations"


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


@pytest.fixture
def org_and_agent(db_session):
    """Create an organization, owner user, and a real agent for FK integrity."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    org = Organization(id=str(org_id), name=f"Org {org_id}", slug=f"org-{org_id}")
    user = User(
        id=str(user_id),
        email=f"owner-{user_id}@example.com",
        is_active=True,
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$...",
    )
    db_session.add_all([org, user])
    db_session.flush()

    agent = Agent(
        organization_id=str(org_id),
        data={
            "name": "Test Agent",
            "system_prompt": "You are a test agent.",
            "public_id": f"test-agent-{org_id}",
        },
    )
    # The Agent model overrides the base `id` without a server_default, so an
    # explicit id is required for an ORM insert (the API never inserts agents,
    # it only reads them via the repository, so this does not affect endpoints).
    agent.id = uuid.uuid4()
    db_session.add(agent)

    member = OrganizationMember(
        organization_id=str(org_id),
        user_id=str(user_id),
        role="owner",
    )
    member.id = uuid.uuid4()
    db_session.add(member)
    db_session.commit()
    db_session.refresh(agent)

    yield str(org_id), str(agent.id)

    # Cleanup: conversations/messages created via the API first, then fixtures.
    db_session.query(Message).filter(Message.organization_id == org_id).delete(
        synchronize_session=False
    )
    db_session.query(Conversation).filter(
        Conversation.organization_id == org_id
    ).delete(synchronize_session=False)
    db_session.delete(member)
    db_session.delete(agent)
    db_session.delete(user)
    db_session.delete(org)
    db_session.commit()


# ---------------------------------------------------------------------------
# POST /conversations
# ---------------------------------------------------------------------------


def test_create_conversation_returns_201(client, org_and_agent):
    org_id, agent_id = org_and_agent
    payload = {
        "agent_id": agent_id,
        "session_id": f"session-{uuid.uuid4()}",
        "user_identifier": "tester@example.com",
        "status": "active",
    }
    response = client.post(f"{API_PREFIX}/?organization_id={org_id}", json=payload)
    assert response.status_code == 201

    body = response.json()
    assert body["organization_id"] == org_id
    assert body["agent_id"] == agent_id
    assert body["session_id"] == payload["session_id"]
    assert body["status"] == "active"
    assert "id" in body


def test_create_conversation_defaults_status(client, org_and_agent):
    org_id, agent_id = org_and_agent
    payload = {
        "agent_id": agent_id,
        "session_id": f"session-{uuid.uuid4()}",
    }
    response = client.post(f"{API_PREFIX}/?organization_id={org_id}", json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "active"


def test_create_conversation_requires_organization_id(client, org_and_agent):
    _, agent_id = org_and_agent
    payload = {
        "agent_id": agent_id,
        "session_id": f"session-{uuid.uuid4()}",
    }
    # Missing required query parameter -> 422 (FastAPI validation).
    response = client.post(f"{API_PREFIX}/", json=payload)
    assert response.status_code == 422


def test_create_conversation_invalid_organization_id(client, org_and_agent):
    _, agent_id = org_and_agent
    payload = {
        "agent_id": agent_id,
        "session_id": f"session-{uuid.uuid4()}",
    }
    response = client.post(
        f"{API_PREFIX}/?organization_id=not-a-uuid", json=payload
    )
    assert response.status_code == 422


def test_create_conversation_validation_error_missing_session(client, org_and_agent):
    org_id, agent_id = org_and_agent
    # session_id is required on ConversationCreate.
    response = client.post(
        f"{API_PREFIX}/?organization_id={org_id}",
        json={"agent_id": agent_id},
    )
    assert response.status_code == 422


def test_create_conversation_invalid_agent_id(client, org_and_agent):
    org_id, _ = org_and_agent
    payload = {
        "agent_id": "not-a-uuid",
        "session_id": f"session-{uuid.uuid4()}",
    }
    response = client.post(f"{API_PREFIX}/?organization_id={org_id}", json=payload)
    assert response.status_code == 400


def test_create_conversation_unknown_agent_404(client, org_and_agent):
    org_id, _ = org_and_agent
    payload = {
        "agent_id": str(uuid.uuid4()),
        "session_id": f"session-{uuid.uuid4()}",
    }
    response = client.post(f"{API_PREFIX}/?organization_id={org_id}", json=payload)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /conversations
# ---------------------------------------------------------------------------


def test_list_conversations_empty(client, org_and_agent):
    org_id, _ = org_and_agent
    response = client.get(f"{API_PREFIX}/?organization_id={org_id}")
    assert response.status_code == 200
    assert response.json() == []


def test_list_conversations_returns_created(client, org_and_agent):
    org_id, agent_id = org_and_agent
    payload = {
        "agent_id": agent_id,
        "session_id": f"session-{uuid.uuid4()}",
    }
    create = client.post(f"{API_PREFIX}/?organization_id={org_id}", json=payload)
    assert create.status_code == 201

    response = client.get(f"{API_PREFIX}/?organization_id={org_id}")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == create.json()["id"]


def test_list_conversations_requires_organization_id(client, org_and_agent):
    response = client.get(f"{API_PREFIX}/")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /conversations/{id}/messages
# ---------------------------------------------------------------------------


def _create_conversation(client, org_id, agent_id):
    payload = {
        "agent_id": agent_id,
        "session_id": f"session-{uuid.uuid4()}",
    }
    response = client.post(f"{API_PREFIX}/?organization_id={org_id}", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def test_create_message_returns_201(client, org_and_agent):
    org_id, agent_id = org_and_agent
    conversation_id = _create_conversation(client, org_id, agent_id)

    payload = {"role": "user", "content": "Hello there"}
    response = client.post(
        f"{API_PREFIX}/{conversation_id}/messages?organization_id={org_id}",
        json=payload,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["conversation_id"] == conversation_id
    assert body["organization_id"] == org_id
    assert body["role"] == "user"
    assert body["content"] == "Hello there"
    assert "id" in body


def test_create_message_invalid_conversation_id(client, org_and_agent):
    org_id, _ = org_and_agent
    payload = {"role": "user", "content": "Hello"}
    # Invalid path UUID -> 422 (FastAPI validation).
    response = client.post(
        f"{API_PREFIX}/not-a-uuid/messages?organization_id={org_id}",
        json=payload,
    )
    assert response.status_code == 422


def test_create_message_unknown_conversation_404(client, org_and_agent):
    org_id, _ = org_and_agent
    payload = {"role": "user", "content": "Hello"}
    response = client.post(
        f"{API_PREFIX}/{uuid.uuid4()}/messages?organization_id={org_id}",
        json=payload,
    )
    assert response.status_code == 404


def test_create_message_requires_organization_id(client, org_and_agent):
    org_id, agent_id = org_and_agent
    conversation_id = _create_conversation(client, org_id, agent_id)
    payload = {"role": "user", "content": "Hello"}
    response = client.post(
        f"{API_PREFIX}/{conversation_id}/messages", json=payload
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /conversations/{id}/messages
# ---------------------------------------------------------------------------


def test_list_messages_empty(client, org_and_agent):
    org_id, agent_id = org_and_agent
    conversation_id = _create_conversation(client, org_id, agent_id)

    response = client.get(
        f"{API_PREFIX}/{conversation_id}/messages?organization_id={org_id}"
    )
    assert response.status_code == 200
    assert response.json() == []


def test_list_messages_returns_created(client, org_and_agent):
    org_id, agent_id = org_and_agent
    conversation_id = _create_conversation(client, org_id, agent_id)

    payload = {"role": "assistant", "content": "Hi! How can I help?"}
    created = client.post(
        f"{API_PREFIX}/{conversation_id}/messages?organization_id={org_id}",
        json=payload,
    )
    assert created.status_code == 201

    response = client.get(
        f"{API_PREFIX}/{conversation_id}/messages?organization_id={org_id}"
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["content"] == "Hi! How can I help?"
    assert body[0]["role"] == "assistant"


def test_list_messages_invalid_conversation_id(client, org_and_agent):
    org_id, _ = org_and_agent
    # Invalid path UUID -> 422 (FastAPI validation).
    response = client.get(
        f"{API_PREFIX}/not-a-uuid/messages?organization_id={org_id}"
    )
    assert response.status_code == 422


def test_list_messages_unknown_conversation_404(client, org_and_agent):
    org_id, _ = org_and_agent
    response = client.get(
        f"{API_PREFIX}/{uuid.uuid4()}/messages?organization_id={org_id}"
    )
    assert response.status_code == 404


def test_list_messages_requires_organization_id(client, org_and_agent):
    org_id, agent_id = org_and_agent
    conversation_id = _create_conversation(client, org_id, agent_id)
    response = client.get(f"{API_PREFIX}/{conversation_id}/messages")
    assert response.status_code == 422
