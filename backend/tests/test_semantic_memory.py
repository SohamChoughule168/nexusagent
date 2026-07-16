"""Semantic Memory retrieval tests (Milestone 5, Phase 2.3).

Tests the semantic (vector) retrieval over ``Memory.embedding`` provided by
``SemanticMemoryRetriever`` and the ``LongTermMemoryService.retrieve_semantic*``
wrappers.

Coverage required by the phase:
* semantic retrieval (relevant memory recalled)
* similarity ranking (descending by cosine)
* top-k retrieval (capped to K, highest-relevance first)
* tenant isolation (no cross-org leakage during vector retrieval)
* regression safety (existing CRUD / keyword search / conversation memory and
  embedding-population are untouched by the new read path)

It reuses the test harness from ``test_long_term_memory`` (DB-backed session +
auth-registered orgs) so tenant isolation is exercised against the real
``RepositoryFactory`` scoping, not a mock.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.all_models import Agent, Conversation, Memory
from app.repositories.tenant_repository import RepositoryFactory
from app.services.embeddings import LocalDeterministicEmbedder
from app.services.long_term_memory import LongTermMemoryService
from app.services.semantic_memory import (
    SemanticMemoryRetriever,
    get_semantic_memory_retriever,
)

AUTH_PREFIX = "/api/v1/auth"


# ---------------------------------------------------------------------------
# Fixtures (mirror test_long_term_memory.py)
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
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": f"sem-owner-{uuid.uuid4()}@example.com",
            "password": "TestPass#123",
            "full_name": "Sem Owner",
            "organization_name": f"Sem Org {uuid.uuid4()}",
            "organization_slug": f"sem-org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _create_agent(db_session, org_id):
    agent = Agent(
        organization_id=org_id,
        data={
            "name": "Sem Agent",
            "system_prompt": "You are a helpful assistant.",
            "public_id": f"sem-agent-{uuid.uuid4()}",
        },
    )
    agent.id = uuid.uuid4()
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


def _make_service(db_session, org_id) -> LongTermMemoryService:
    return LongTermMemoryService(db_session, org_id)


# ---------------------------------------------------------------------------
# Semantic retrieval — relevance
# ---------------------------------------------------------------------------


def test_semantic_retrieval_returns_relevant_memory(db_session, client):
    """A semantically related query recalls the closest memory first."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    service.create_memory(
        content="The user loves pizza and Italian food.", category="preference"
    )
    service.create_memory(
        content="The user prefers tea over coffee.", category="preference"
    )
    service.create_memory(
        content="The project deadline is next Friday.", category="fact"
    )

    results = service.retrieve_semantic("Tell me about pizza and Italian cuisine")
    assert len(results) >= 1
    assert "pizza" in results[0].content
    assert "Italian" in results[0].content


def test_semantic_retrieval_via_standalone_retriever(db_session, client):
    """The decoupled SemanticMemoryRetriever works without the service."""
    token, org_id = _register(client)
    retriever = SemanticMemoryRetriever(db_session, org_id)
    embedder = LocalDeterministicEmbedder()
    repo = retriever.repository_factory.memories()

    # Standalone insert path: provide the embedding the retriever ranks on
    # (the service normally populates it; here we mirror that explicitly).
    m1 = Memory(
        organization_id=org_id,
        content="The user loves pizza and Italian food.",
        category="preference",
    )
    m1.embedding = embedder.embed([m1.content])[0]
    repo.create(m1)

    m2 = Memory(
        organization_id=org_id,
        content="The user prefers tea over coffee.",
        category="preference",
    )
    m2.embedding = embedder.embed([m2.content])[0]
    repo.create(m2)

    results = retriever.retrieve("Italian food and pizza preferences")
    assert results[0].content == "The user loves pizza and Italian food."


# ---------------------------------------------------------------------------
# Similarity ranking
# ---------------------------------------------------------------------------


def test_similarity_ranking_descending(db_session, client):
    """Results are ordered by descending cosine similarity to the query."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    service.create_memory(content="The user loves pizza and Italian food.")
    service.create_memory(content="The user prefers tea over coffee.")
    service.create_memory(content="The project deadline is next Friday.")

    scored = service.retrieve_semantic_scored("pizza and Italian food preferences")
    assert len(scored) >= 2

    scores = [s for s, _ in scored]
    # Strictly descending.
    assert scores == sorted(scores, reverse=True)
    # The pizza memory outranks the unrelated deadline memory.
    pizza_score = next(s for s, m in scored if "pizza" in m.content)
    deadline_score = next(s for s, m in scored if "deadline" in m.content)
    assert pizza_score > deadline_score


def test_semantic_scored_returns_pairs_with_scores(db_session, client):
    """retrieve_semantic_scored returns (Memory, score) tuples in [0,1]-ish."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    service.create_memory(content="The user loves pizza and Italian food.")
    service.create_memory(content="The user prefers tea over coffee.")

    scored = service.retrieve_semantic_scored("pizza")
    assert all(isinstance(mem, Memory) for _, mem in scored)
    assert all(isinstance(score, float) for score, _ in scored)
    assert all(-1.0 <= score <= 1.0 for score, _ in scored)


# ---------------------------------------------------------------------------
# Top-K retrieval
# ---------------------------------------------------------------------------


def test_top_k_caps_result_count(db_session, client):
    """top_k limits the number of returned memories."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    for i in range(6):
        service.create_memory(
            content=f"Distinct memory number {i} about various unrelated topics."
        )

    # Query touching a couple of memories; cap to 2.
    results = service.retrieve_semantic("memory number", top_k=2)
    assert len(results) <= 2
    # And the unrestricted query returns more than the capped one.
    all_results = service.retrieve_semantic("memory number", top_k=10)
    assert len(all_results) >= 3
    assert len(results) <= len(all_results)


def test_top_k_returns_highest_relevance_first(db_session, client):
    """With top_k < candidates, the returned set is the most relevant subset."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    service.create_memory(content="The user loves pizza and Italian food.")
    service.create_memory(content="The user prefers tea over coffee.")
    service.create_memory(content="The user enjoys hiking on weekends.")
    service.create_memory(content="The user reads science fiction novels.")

    top2 = service.retrieve_semantic("pizza and Italian cuisine", top_k=2)
    assert len(top2) == 2
    assert "pizza" in top2[0].content


def test_retrieve_excludes_memories_without_embedding(db_session, client):
    """Memories lacking an embedding are never returned by semantic retrieval."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    repo = service.repository_factory.memories()

    with_embedding = service.create_memory(content="The user loves pizza.")
    # Directly insert a memory row with no embedding to mimic a legacy/empty vec.
    bare = Memory(organization_id=org_id, content="The user loves pizza too.")
    bare.embedding = None
    repo.create(bare)

    results = service.retrieve_semantic("pizza")
    ids = {m.id for m in results}
    assert with_embedding.id in ids
    assert bare.id not in ids

    repo.delete(bare)


# ---------------------------------------------------------------------------
# min_similarity threshold
# ---------------------------------------------------------------------------


def test_min_similarity_threshold_filters(db_session, client):
    """A high min_similarity excludes weakly-matching memories."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    service.create_memory(content="The user loves pizza and Italian food.")
    service.create_memory(content="The user prefers tea over coffee.")

    # No memory is near-identical to this query, so a very high threshold drops
    # everything.
    strict = service.retrieve_semantic("pizza", min_similarity=0.999)
    assert strict == []

    # A relaxed threshold still returns results.
    relaxed = service.retrieve_semantic("pizza", min_similarity=0.0)
    assert len(relaxed) >= 1


def test_exact_duplicate_scores_near_one(db_session, client):
    """A query identical to a memory content scores ~1.0 (cosine on itself)."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    service.create_memory(content="The user loves pizza and Italian food.")
    scored = service.retrieve_semantic_scored(
        "The user loves pizza and Italian food.", min_similarity=0.0
    )
    assert scored
    top_score, top_mem = scored[0]
    assert top_score > 0.9
    assert "pizza" in top_mem.content


# ---------------------------------------------------------------------------
# Empty / degenerate inputs
# ---------------------------------------------------------------------------


def test_semantic_retrieval_empty_query(db_session, client):
    """A blank query returns nothing (no scoring on empty text)."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    service.create_memory(content="The user loves pizza.")

    assert service.retrieve_semantic("   ") == []
    assert service.retrieve_semantic("") == []


def test_semantic_retrieval_no_memories(db_session, client):
    """Semantic retrieval on an empty tenant returns []. """
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    assert service.retrieve_semantic("anything") == []


# ---------------------------------------------------------------------------
# format_for_prompt (reuse helper for Chat / Orchestrator / Router)
# ---------------------------------------------------------------------------


def test_format_for_prompt_renders_memories(db_session, client):
    """format_for_prompt renders recalled memories into an LLM context block."""
    token, org_id = _register(client)
    retriever = SemanticMemoryRetriever(db_session, org_id)
    mems = [
        Memory(organization_id=org_id, content="Prefers dark mode.", category="preference"),
        Memory(organization_id=org_id, content="Works in UTC.", category="fact"),
    ]
    block = retriever.format_for_prompt(mems)
    assert "Prefers dark mode." in block
    assert "Works in UTC." in block
    assert "[preference]" in block
    assert "[fact]" in block


def test_format_for_prompt_empty(db_session, client):
    """Empty input yields an empty string so callers can skip injection."""
    token, org_id = _register(client)
    retriever = SemanticMemoryRetriever(db_session, org_id)
    assert retriever.format_for_prompt([]) == ""


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_tenant_isolation_semantic_retrieval(db_session, client):
    """Vector retrieval never crosses tenant boundaries."""
    token_a, org_a = _register(client)
    token_b, org_b = _register(client)

    service_a = _make_service(db_session, org_a)
    service_b = _make_service(db_session, org_b)

    # Same content in both tenants (identical embedding), different orgs.
    mem_a = service_a.create_memory(
        content="The user loves pizza and Italian food.", key="food", category="preference"
    )
    mem_b = service_b.create_memory(
        content="The user loves pizza and Italian food.", key="food", category="preference"
    )

    # Org B's semantic retrieval must return ONLY Org B's memory.
    results_b = service_b.retrieve_semantic("user loves pizza and Italian food")
    assert len(results_b) >= 1
    assert all(str(m.organization_id) == org_b for m in results_b)
    assert results_b[0].id == mem_b.id
    # Critically, Org A's memory is never returned to Org B.
    assert mem_a.id not in {m.id for m in results_b}

    # Symmetric check for Org A.
    results_a = service_a.retrieve_semantic("user loves pizza and Italian food")
    assert all(str(m.organization_id) == org_a for m in results_a)
    assert mem_a.id in {m.id for m in results_a}
    assert mem_b.id not in {m.id for m in results_a}


def test_tenant_isolation_standalone_retriever(db_session, client):
    """The standalone retriever is also tenant-scoped via RepositoryFactory."""
    token_a, org_a = _register(client)
    token_b, org_b = _register(client)

    retriever_a = SemanticMemoryRetriever(db_session, org_a)
    retriever_b = SemanticMemoryRetriever(db_session, org_b)
    embedder = LocalDeterministicEmbedder()

    mem_a = Memory(organization_id=org_a, content="Org A confidential fact.", category="fact")
    mem_a.embedding = embedder.embed([mem_a.content])[0]
    retriever_a.repository_factory.memories().create(mem_a)

    mem_b = Memory(organization_id=org_b, content="Org B confidential fact.", category="fact")
    mem_b.embedding = embedder.embed([mem_b.content])[0]
    retriever_b.repository_factory.memories().create(mem_b)

    # Retriever B sees only B's memories even when querying A's content.
    out_b = retriever_b.retrieve("confidential fact")
    assert all(str(m.organization_id) == org_b for m in out_b)
    assert mem_b.id in {m.id for m in out_b}
    assert mem_a.id not in {m.id for m in out_b}


def test_retriever_factory_builds_scoped_instance(db_session, client):
    """DI factory builds a correctly scoped standalone retriever."""
    token, org_id = _register(client)
    retriever = get_semantic_memory_retriever(db_session, org_id)
    assert isinstance(retriever, SemanticMemoryRetriever)
    assert retriever.organization_id == org_id


# ---------------------------------------------------------------------------
# Regression safety
# ---------------------------------------------------------------------------


def test_regression_existing_crud_unaffected(db_session, client):
    """Adding semantic retrieval does not change CRUD / keyword behavior."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    m1 = service.create_memory(
        content="The user dislikes cold emails.", category="preference", key="email_pref"
    )
    # Keyword search still works (non-semantic path untouched).
    hits = service.search_by_content("cold")
    assert len(hits) == 1 and "cold" in hits[0].content

    # CRUD still works.
    assert service.get_by_key("email_pref").id == m1.id
    service.update_memory(m1.id, content="The user dislikes spam emails.")
    assert "spam" in service.get_memory(m1.id).content
    assert service.count() == 1
    assert service.delete_memory(m1.id) is True
    assert service.count() == 0


def test_regression_embedding_populated_on_write(db_session, client):
    """Memories still carry a populated embedding after semantic retrieval added."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    mem = service.create_memory(content="The user loves pizza.")
    assert mem.embedding is not None and len(mem.embedding) > 0

    # Updating content republishes the embedding (unchanged behavior).
    old = list(mem.embedding)
    updated = service.update_memory(mem.id, content="The user loves pasta.")
    assert updated.embedding != old
    service.delete_memory(mem.id)


def test_regression_conversation_memory_untouched(db_session, client):
    """Semantic retrieval is independent of Conversation Memory logic."""
    from app.services.conversation_memory import ConversationMemoryService

    token, org_id = _register(client)
    # Build a conversation so ConversationMemoryService has real state to protect.
    repo_factory = RepositoryFactory(db_session, org_id)
    agent = _create_agent(db_session, org_id)
    conv = Conversation(
        organization_id=org_id,
        agent_id=agent.id,
        session_id=f"sem-sess-{uuid.uuid4()}",
    )
    conv.id = uuid.uuid4()
    repo_factory.conversations().create(conv)
    service = _make_service(db_session, org_id)
    service.create_memory(content="The user loves pizza.")

    # Semantic retrieval runs without disturbing ConversationMemoryService.
    cm = ConversationMemoryService(db_session, org_id)
    retrieved = service.retrieve_semantic("pizza")
    assert len(retrieved) == 1

    # Conversation memory still functions normally afterwards.
    ctx, _, _ = cm.build_context(conv.id, "ignored query")
    assert ctx is not None

    repo_factory.conversations().delete(conv)
    db_session.delete(agent)
    db_session.commit()


def test_regression_agent_scoped_retrieval(db_session, client):
    """Semantic retrieval can be scoped to an agent without breaking isolation."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    agent = _create_agent(db_session, org_id)

    service.create_memory(
        content="The user loves pizza.", agent_id=agent.id, category="preference"
    )
    service.create_memory(content="The user prefers tea.", category="preference")

    # Scoped to the agent -> only the agent's memory.
    scoped = service.retrieve_semantic("pizza", agent_id=agent.id)
    assert len(scoped) == 1
    assert scoped[0].agent_id == agent.id

    # Unscoped -> both memories considered.
    all_results = service.retrieve_semantic("preferences")
    assert len(all_results) == 2

    service.delete_memory(scoped[0].id)
    other = service.list_memories()[0]
    service.delete_memory(other.id)
    db_session.delete(agent)
    db_session.commit()
