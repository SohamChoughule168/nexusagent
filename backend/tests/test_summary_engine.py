"""Conversation Summary Engine tests (Milestone5, Phase2.1).

Covers the six Phase2.1 deliverables:

* **Summary generation** -- :meth:`ConversationMemoryService.generate_summary`
  calls the LLM and persists a summary into the existing ``Conversation.summary``
  field (no schema change), and *extends* an existing summary (iterative
  summarization) rather than restarting.
* **Threshold-based generation** -- :meth:`should_summarize` /
  :meth:`maybe_generate_summary` fire only after configurable message/token
  thresholds are crossed (safe no-op below threshold / offline).
* **Summary retrieval + context injection** -- :meth:`build_context` injects the
  summary *first*, then the recent token-budgeted history (replacing old
  messages with the summary), then leaves room for RAG context.
* **Tenant isolation** -- summaries are organization-scoped; a service bound to
  org B cannot read org A's summary.
* **Regression safety** -- ``build_context`` with no summary behaves exactly
  like the prior history injection (query-only when there is no history).

Async methods are exercised synchronously via ``asyncio.run`` (no
``pytest-asyncio`` dependency), matching the rest of the backend suite.
"""
import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.ai.providers.base import GenerationRequest, GenerationResponse, TokenUsage
from app.main import app
from app.models.all_models import Agent, Conversation, Message
from app.repositories.tenant_repository import RepositoryFactory
from app.services.conversation_memory import ConversationMemoryService


CONV_PREFIX = "/api/v1/conversations"
AUTH_PREFIX = "/api/v1/auth"


def _run(coro):
    """Run a coroutine to completion (no pytest-asyncio dependency)."""
    return asyncio.run(coro)


class _StubProvider:
    """Deterministic in-memory LLM provider for summary-generation tests.

    Records the last :class:`GenerationRequest` it received so tests can assert
    on the prompt that was built, and returns a fixed summary string.
    """

    def __init__(self, content: str = "SUMMARY TEXT"):
        self.content = content
        self.last_request: GenerationRequest = None

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.last_request = request
        return GenerationResponse(
            content=self.content,
            token_usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )

    async def close(self):
        return None


# ---------------------------------------------------------------------------
# Fixtures (mirror test_conversation_memory.py)
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
    email = f"sum-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Summary Owner",
            "organization_name": f"Summary Org {uuid.uuid4()}",
            "organization_slug": f"sum-org-{uuid.uuid4()}",
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
            "name": "Summary Agent",
            "system_prompt": "You are a helpful assistant.",
            "public_id": f"sum-agent-{uuid.uuid4()}",
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
    """Create test messages for a conversation (returns the messages)."""
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


def _set_message_count(db_session, org_id, conversation_id, count: int):
    """Force Conversation.message_count (used to drive summarize thresholds)."""
    rf = RepositoryFactory(db_session, org_id)
    conv = rf.conversations().get(conversation_id)
    conv.message_count = count
    rf.conversations().update(conv)


# ---------------------------------------------------------------------------
# Summary generation (creates + persists)
# ---------------------------------------------------------------------------


def test_generate_summary_persists_and_returns(db_session, client):
    """generate_summary calls the LLM and stores the summary in Conversation.summary."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)
    _create_messages(db_session, org_id, conv_id, count=3)

    service = ConversationMemoryService(db_session, org_id)
    stub = _StubProvider(content="The user asked about quantum physics.")

    summary = _run(service.generate_summary(conv_id, provider=stub))

    assert summary == "The user asked about quantum physics."
    # Persisted into the existing field.
    assert service.get_conversation_summary(conv_id) == summary
    # The LLM was given the conversation history to summarize.
    assert stub.last_request is not None
    user_msg = stub.last_request.messages[-1].content
    assert "Test message" in user_msg

    # Cleanup
    db_session.query(Message).filter(Message.conversation_id == str(conv_id)).delete()
    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete()
    db_session.delete(agent)
    db_session.commit()


def test_generate_summary_extends_existing(db_session, client):
    """When a summary already exists, generate_summary extends it (iterative)."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)
    _create_messages(db_session, org_id, conv_id, count=2)

    service = ConversationMemoryService(db_session, org_id)
    # Seed an existing summary.
    assert service.update_conversation_summary(conv_id, "Existing context about billing.")

    stub = _StubProvider(content="Updated summary including billing and refunds.")
    summary = _run(service.generate_summary(conv_id, provider=stub))

    assert summary == "Updated summary including billing and refunds."
    assert service.get_conversation_summary(conv_id) == summary
    # The existing summary was passed back to the LLM for extension.
    assert "Existing context about billing." in stub.last_request.messages[-1].content

    db_session.query(Message).filter(Message.conversation_id == str(conv_id)).delete()
    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete()
    db_session.delete(agent)
    db_session.commit()


def test_generate_summary_no_history_returns_existing(db_session, client):
    """With no messages, generate_summary keeps any existing summary untouched."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    service = ConversationMemoryService(db_session, org_id)
    service.update_conversation_summary(conv_id, "Pre-existing summary")

    stub = _StubProvider(content="SHOULD NOT BE USED")
    summary = _run(service.generate_summary(conv_id, provider=stub))

    assert summary == "Pre-existing summary"
    # The LLM was never called (no history to summarize).
    assert stub.last_request is None

    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete()
    db_session.delete(agent)
    db_session.commit()


def test_generate_summary_unknown_conversation_returns_none(db_session, client):
    """generate_summary returns None for a conversation that does not exist."""
    token, org_id = _register(client)
    service = ConversationMemoryService(db_session, org_id)

    summary = _run(service.generate_summary(uuid.uuid4(), provider=_StubProvider()))
    assert summary is None


# ---------------------------------------------------------------------------
# Threshold-based automatic generation
# ---------------------------------------------------------------------------


def test_should_summarize_respects_message_threshold(db_session, client):
    """should_summarize is False below the message threshold, True above it."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    service = ConversationMemoryService(db_session, org_id)
    # New conversation (message_count 0) is below the default threshold.
    assert service.should_summarize(conv_id) is False

    # Push message count above the default threshold.
    _set_message_count(db_session, org_id, conv_id, 21)
    assert service.should_summarize(conv_id) is True

    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete()
    db_session.delete(agent)
    db_session.commit()


def test_should_summarize_respects_token_threshold(db_session, client):
    """should_summarize triggers on estimated history tokens when count is low."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)
    # Long messages so the token estimate crosses a tiny threshold.
    for i in range(5):
        msg = Message(
            conversation_id=str(conv_id),
            organization_id=str(org_id),
            role="user",
            content="word " * 200,  # ~200 tokens each
            token_count=200,
        )
        msg.id = uuid.uuid4()
        db_session.add(msg)
    db_session.commit()

    service = ConversationMemoryService(db_session, org_id)
    # Far above any realistic count -> False.
    assert service.should_summarize(conv_id, token_threshold=1_000_000) is False
    # Tiny threshold -> the long history crosses it -> True.
    assert service.should_summarize(conv_id, token_threshold=10) is True

    db_session.query(Message).filter(Message.conversation_id == str(conv_id)).delete()
    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete()
    db_session.delete(agent)
    db_session.commit()


def test_maybe_generate_summary_fires_only_above_threshold(db_session, client):
    """maybe_generate_summary generates above threshold, no-ops below it."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)
    _create_messages(db_session, org_id, conv_id, count=3)
    stub = _StubProvider(content="Auto summary.")

    service = ConversationMemoryService(db_session, org_id)
    # Below threshold -> no generation, returns None, LLM unused.
    result = _run(service.maybe_generate_summary(conv_id, message_threshold=20, provider=stub))
    assert result is None
    assert stub.last_request is None

    # Cross the threshold -> generates and persists.
    _set_message_count(db_session, org_id, conv_id, 21)
    result = _run(service.maybe_generate_summary(conv_id, message_threshold=20, provider=stub))
    assert result == "Auto summary."
    assert service.get_conversation_summary(conv_id) == "Auto summary."

    db_session.query(Message).filter(Message.conversation_id == str(conv_id)).delete()
    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete()
    db_session.delete(agent)
    db_session.commit()


# ---------------------------------------------------------------------------
# Context injection using summaries
# ---------------------------------------------------------------------------


def test_build_context_injects_summary_first(db_session, client):
    """build_context injects the summary before the recent history."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)
    _create_messages(db_session, org_id, conv_id, count=3)

    service = ConversationMemoryService(db_session, org_id)
    service.update_conversation_summary(conv_id, "The user is planning a trip to Japan.")

    prompt, summary, history = service.build_context(conv_id, "Any hotel tips?")

    assert summary == "The user is planning a trip to Japan."
    assert "Conversation summary:" in prompt
    assert "The user is planning a trip to Japan." in prompt
    assert "Recent conversation:" in prompt
    assert "Any hotel tips?" in prompt
    # Summary block precedes the recent-history block.
    assert prompt.index("Conversation summary:") < prompt.index("Recent conversation:")
    assert len(history) > 0

    db_session.query(Message).filter(Message.conversation_id == str(conv_id)).delete()
    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete()
    db_session.delete(agent)
    db_session.commit()


def test_build_context_without_summary_uses_history_only(db_session, client):
    """With no summary, build_context uses recent history (matches prior behavior)."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)
    _create_messages(db_session, org_id, conv_id, count=2)

    service = ConversationMemoryService(db_session, org_id)
    assert service.get_conversation_summary(conv_id) is None

    prompt, summary, history = service.build_context(conv_id, "Hello again?")

    assert summary is None
    assert "Conversation summary:" not in prompt
    assert "Recent conversation:" in prompt
    assert "Hello again?" in prompt
    assert history  # recent history was injected

    db_session.query(Message).filter(Message.conversation_id == str(conv_id)).delete()
    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete()
    db_session.delete(agent)
    db_session.commit()


def test_build_context_no_history_no_summary_returns_query(db_session, client):
    """Regression safety: empty conversation yields just the query."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)

    service = ConversationMemoryService(db_session, org_id)
    prompt, summary, history = service.build_context(conv_id, "Standalone question?")

    assert summary is None
    assert history == []
    assert prompt == "Current query: Standalone question?"

    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete()
    db_session.delete(agent)
    db_session.commit()


def test_build_context_shrinks_history_window_when_summary_present(db_session, client):
    """Token optimization: a summary shrinks the recent-history budget."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)
    _create_messages(db_session, org_id, conv_id, count=10)

    service = ConversationMemoryService(db_session, org_id)
    # No summary -> full window, more recent messages retained.
    _, _, history_no_summary = service.build_context(conv_id, "q", max_context_tokens=2000)
    # With summary -> window shrinks, fewer recent messages retained.
    service.update_conversation_summary(conv_id, "Condensed prior context.")
    _, _, history_with_summary = service.build_context(conv_id, "q", max_context_tokens=2000)

    assert len(history_with_summary) <= len(history_no_summary)

    db_session.query(Message).filter(Message.conversation_id == str(conv_id)).delete()
    db_session.query(Conversation).filter(Conversation.id == str(conv_id)).delete()
    db_session.delete(agent)
    db_session.commit()


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_summary_engine_respects_tenant_isolation(db_session, client):
    """Org B's service cannot read Org A's summary (organization-scoped)."""
    token_a, org_a = _register(client)
    token_b, org_b = _register(client)

    agent_a = _create_agent(db_session, org_a)
    agent_b = _create_agent(db_session, org_b)
    conv_a = _create_conversation(client, token_a, agent_a.id)
    _create_conversation(client, token_b, agent_b.id)

    service_a = ConversationMemoryService(db_session, org_a)
    service_b = ConversationMemoryService(db_session, org_b)

    # Org A writes a summary on its own conversation.
    assert service_a.update_conversation_summary(conv_a, "Org A secret context")

    # Org B must NOT see Org A's summary (the conversation is invisible to B).
    assert service_b.get_conversation_summary(conv_a) is None
    # Org B's build_context for A's conversation yields no summary/history.
    prompt_b, summary_b, history_b = service_b.build_context(conv_a, "hi")
    assert summary_b is None
    assert history_b == []
    assert prompt_b == "Current query: hi"

    # Cleanup
    db_session.query(Conversation).filter(Conversation.organization_id == str(org_a)).delete()
    db_session.query(Conversation).filter(Conversation.organization_id == str(org_b)).delete()
    db_session.query(Agent).filter(Agent.organization_id == str(org_a)).delete()
    db_session.query(Agent).filter(Agent.organization_id == str(org_b)).delete()
    db_session.commit()


def test_generate_summary_cannot_summarize_cross_tenant(db_session, client):
    """generate_summary safely returns None for a conversation in another org."""
    token_a, org_a = _register(client)
    token_b, org_b = _register(client)
    agent_a = _create_agent(db_session, org_a)
    conv_a = _create_conversation(client, token_a, agent_a.id)

    # Service bound to org B attempts to summarize org A's conversation.
    service_b = ConversationMemoryService(db_session, org_b)
    summary = _run(service_b.generate_summary(conv_a, provider=_StubProvider()))

    assert summary is None

    db_session.query(Conversation).filter(Conversation.organization_id == str(org_a)).delete()
    db_session.query(Agent).filter(Agent.organization_id == str(org_a)).delete()
    db_session.query(Agent).filter(Agent.organization_id == str(org_b)).delete()
    db_session.commit()
