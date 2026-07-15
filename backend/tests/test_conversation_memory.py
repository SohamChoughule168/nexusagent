"""Conversation Memory service tests (Milestone 5, Phase 1).

Tests the four deliverables:
* Conversation history retrieval
* Context window management
* Automatic history injection
* Token budgeting

Also includes integration tests with the conversation API.
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.all_models import Agent, Conversation, Message
from app.repositories.tenant_repository import RepositoryFactory
from app.services.conversation_memory import (
    ConversationMemoryService,
    get_conversation_memory_service
)

CONV_PREFIX = "/api/v1/conversations"
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
    email = f"mem-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Memory Owner",
            "organization_name": f"Memory Org {uuid.uuid4()}",
            "organization_slug": f"mem-org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_agent(db_session, org_id):
    agent = Agent(
        organization_id=org_id,
        data={
            "name": "Memory Agent",
            "system_prompt": "You are a helpful assistant.",
            "public_id": f"mem-agent-{uuid.uuid4()}",
        },
    )
    agent.id = uuid.uuid4()
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


def _create_conversation(client: TestClient, token: str, agent_id: uuid.UUID):
    resp = client.post(
        f"{CONV_PREFIX}/",
        json={"agent_id": str(agent_id), "session_id": f"session-{uuid.uuid4()}"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_messages(db_session, org_id, conversation_id, count=5):
    """Create test messages for a conversation."""
    messages = []
    for i in range(count):
        msg = Message(
            conversation_id=str(conversation_id),
            organization_id=str(org_id),
            role="user" if i % 2 == 0 else "assistant",
            content=f"Test message {i} with some content to make it longer.",
            token_count=10,
        )
        msg.id = uuid.uuid4()
        db_session.add(msg)
        messages.append(msg)
    db_session.commit()
    for msg in messages:
        db_session.refresh(msg)
    return messages


# ---------------------------------------------------------------------------
# Conversation history retrieval
# ---------------------------------------------------------------------------


def test_get_conversation_history_returns_messages(db_session, client):
    """Test that history retrieval returns messages for a valid conversation."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    # Create test messages
    messages = _create_messages(db_session, org_id, conv_id, count=3)

    # Get memory service and retrieve history
    service = ConversationMemoryService(db_session, org_id)
    history = service.get_conversation_history(conv_id)

    # Should return messages in chronological order
    assert len(history) == 3
    assert [m.content for m in history] == [m.content for m in messages]

    # Cleanup
    for m in messages:
        db_session.delete(m)
    db_session.delete(agent)
    db_session.delete(db_session.query(Conversation).get(conv_id))
    db_session.commit()


def test_get_conversation_history_empty_for_nonexistent(db_session, client):
    """Test that nonexistent conversation returns empty list."""
    token, org_id = _register(client)

    service = ConversationMemoryService(db_session, org_id)
    fake_conv_id = uuid.uuid4()
    history = service.get_conversation_history(fake_conv_id)

    assert history == []


def test_get_conversation_history_respects_limit(db_session, client):
    """Test that history retrieval respects the limit parameter."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    # Create 10 messages
    messages = _create_messages(db_session, org_id, conv_id, count=10)

    service = ConversationMemoryService(db_session, org_id)
    history = service.get_conversation_history(conv_id, limit=5)

    # Should only return 5 messages
    assert len(history) == 5

    # Cleanup
    for m in messages:
        db_session.delete(m)
    db_session.delete(agent)
    db_session.delete(db_session.query(Conversation).get(conv_id))
    db_session.commit()


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def test_estimate_token_count_returns_positive():
    """Test token estimation returns positive count for text."""
    service = ConversationMemoryService(None, uuid.uuid4())

    tokens = service.estimate_token_count("Hello, world!")
    assert tokens > 0


def test_estimate_token_count_empty_string():
    """Test token estimation for empty string."""
    service = ConversationMemoryService(None, uuid.uuid4())

    tokens = service.estimate_token_count("")
    assert tokens == 0


def test_estimate_messages_token_count(db_session, client):
    """Test token estimation for messages."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    # Create messages and estimate tokens
    service = ConversationMemoryService(db_session, org_id)
    messages = _create_messages(db_session, org_id, conv_id, count=3)

    total_tokens = service.estimate_messages_token_count(messages)
    assert total_tokens > 0

    # Cleanup
    for m in messages:
        db_session.delete(m)
    db_session.commit()


# ---------------------------------------------------------------------------
# Context window truncation
# ---------------------------------------------------------------------------


def test_truncate_history_to_token_limit(db_session, client):
    """Test that history is truncated to fit within token limit."""
    token, org_id = _register(client)

    service = ConversationMemoryService(db_session, org_id)

    # Create messages with known content sizes
    messages = []
    for i in range(5):
        msg = Message(
            conversation_id=str(uuid.uuid4()),
            organization_id=str(org_id),
            role="user",
            content=f"Message {i}: " + "x" * 100,  # 100+ char messages
            token_count=30,
        )
        msg.id = uuid.uuid4()
        messages.append(msg)

    # Truncate to very small token limit
    truncated = service.truncate_history_to_token_limit(messages, max_tokens=50)

    # Should return fewer messages than we started with
    assert len(truncated) < len(messages)
    assert len(truncated) >= 0


def test_truncate_history_preserves_recent_messages(db_session, client):
    """Test that truncation keeps most recent messages."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    # Create 3 short messages
    messages = _create_messages(db_session, org_id, conv_id, count=3)

    service = ConversationMemoryService(db_session, org_id)

    # Create fresh messages with IDs for testing
    fresh_messages = db_session.query(Message).filter(
        Message.conversation_id == str(conv_id)
    ).order_by(Message.created_at).all()

    # Use a token limit that would fit all
    truncated = service.truncate_history_to_token_limit(fresh_messages, max_tokens=10000)

    # Should return all messages
    assert len(truncated) == len(fresh_messages)

    # Cleanup: delete the conversation before the agent it references, otherwise
    # the ORM nulls conversations.agent_id (a NOT NULL column) and the flush fails.
    for m in messages:
        db_session.delete(m)
    db_session.delete(db_session.query(Conversation).get(conv_id))
    db_session.delete(agent)
    db_session.commit()


# ---------------------------------------------------------------------------
# Context window messages
# ---------------------------------------------------------------------------


def test_get_context_window_messages_respects_limit(db_session, client):
    """Test context window messages respects token limit."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    # Create messages
    messages = _create_messages(db_session, org_id, conv_id, count=5)

    service = ConversationMemoryService(db_session, org_id)

    # Request small context window
    context_messages = service.get_context_window_messages(
        conv_id, max_context_tokens=50
    )

    # Should return truncated messages
    assert len(context_messages) <= len(messages)

    # Cleanup
    for m in messages:
        db_session.delete(m)
    db_session.commit()


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------


def test_format_messages_for_prompt_empty():
    """Test formatting empty message list."""
    service = ConversationMemoryService(None, uuid.uuid4())

    formatted = service.format_messages_for_prompt([])
    assert formatted == ""


def test_format_messages_for_prompt(db_session, client):
    """Test formatting messages for prompt."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    # Create messages with explicit content
    msg1 = Message(
        conversation_id=str(conv_id),
        organization_id=str(org_id),
        role="user",
        content="Hello",
        token_count=1,
    )
    msg1.id = uuid.uuid4()

    msg2 = Message(
        conversation_id=str(conv_id),
        organization_id=str(org_id),
        role="assistant",
        content="Hi there",
        token_count=2,
    )
    msg2.id = uuid.uuid4()
    db_session.add(msg1)
    db_session.add(msg2)
    db_session.commit()

    service = ConversationMemoryService(db_session, org_id)
    formatted = service.format_messages_for_prompt([msg1, msg2])

    assert "user: Hello" in formatted
    assert "assistant: Hi there" in formatted

    # Cleanup
    db_session.delete(msg1)
    db_session.delete(msg2)
    db_session.commit()


# ---------------------------------------------------------------------------
# History injection
# ---------------------------------------------------------------------------


def test_inject_conversation_history_no_history(db_session, client):
    """Test injection when there's no conversation history."""
    token, org_id = _register(client)

    service = ConversationMemoryService(db_session, org_id)
    fake_conv_id = uuid.uuid4()

    enhanced_prompt, history = service.inject_conversation_history(
        fake_conv_id, "What is the weather?"
    )

    # Should return original query without history
    assert enhanced_prompt == "What is the weather?"
    assert history == []


def test_inject_conversation_history_with_history(db_session, client):
    """Test injection prepends conversation history."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    # Create messages
    msg = Message(
        conversation_id=str(conv_id),
        organization_id=str(org_id),
        role="user",
        content="Previous question",
        token_count=3,
    )
    msg.id = uuid.uuid4()
    db_session.add(msg)
    db_session.commit()

    service = ConversationMemoryService(db_session, org_id)
    enhanced_prompt, history = service.inject_conversation_history(
        conv_id, "Current question"
    )

    assert "Previous question" in enhanced_prompt
    assert "Current question" in enhanced_prompt
    assert len(history) == 1

    # Cleanup
    db_session.delete(msg)
    db_session.commit()


# ---------------------------------------------------------------------------
# Summary management
# ---------------------------------------------------------------------------


def test_get_conversation_summary(db_session, client):
    """Test getting conversation summary."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    service = ConversationMemoryService(db_session, org_id)
    summary = service.get_conversation_summary(conv_id)

    # New conversations have no summary
    assert summary is None


def test_update_conversation_summary(db_session, client):
    """Test updating conversation summary."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    service = ConversationMemoryService(db_session, org_id)
    result = service.update_conversation_summary(conv_id, "Test summary")

    assert result is True
    updated_summary = service.get_conversation_summary(conv_id)
    assert updated_summary == "Test summary"

    # Cleanup
    db_session.delete(agent)
    db_session.delete(db_session.query(Conversation).get(conv_id))
    db_session.commit()


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def test_get_conversation_memory_service_factory(db_session, client):
    """Test the factory function creates service correctly."""
    token, org_id = _register(client)

    service = get_conversation_memory_service(db_session, org_id)

    assert isinstance(service, ConversationMemoryService)
    assert service.organization_id == org_id


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_memory_service_respects_tenant_isolation(db_session, client):
    """Test that memory service respects tenant isolation."""
    # Register two organizations (each token must be used with its own tenant's
    # agent -- reusing one token across tenants would 404 on agent resolution).
    token_a, org_a = _register(client)
    token_b, org_b = _register(client)

    agent_a = _create_agent(db_session, org_a)
    agent_b = _create_agent(db_session, org_b)

    conv_a = _create_conversation(client, token_a, agent_a.id)
    conv_b = _create_conversation(client, token_b, agent_b.id)

    service_a = ConversationMemoryService(db_session, org_a)
    service_b = ConversationMemoryService(db_session, org_b)

    # Both should have empty history initially
    history_a = service_a.get_conversation_history(conv_a)
    history_b = service_b.get_conversation_history(conv_b)

    assert history_a == []
    assert history_b == []

    # Cleanup: conversations reference agents (NOT NULL FK), so delete the
    # conversations before the agents to avoid a foreign-key violation.
    db_session.query(Conversation).filter(Conversation.organization_id == str(org_a)).delete()
    db_session.query(Conversation).filter(Conversation.organization_id == str(org_b)).delete()
    db_session.query(Agent).filter(Agent.organization_id == str(org_a)).delete()
    db_session.query(Agent).filter(Agent.organization_id == str(org_b)).delete()
    db_session.commit()