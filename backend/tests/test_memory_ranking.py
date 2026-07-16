"""Memory Ranking tests (Milestone 5, Phase 2.5).

Tests the weighted ranking over long-term memories provided by
``MemoryRanker`` and the ``LongTermMemoryService`` (``rank_memories`` /
``rank_memories_scored``) wrappers.

Coverage required by the phase:
* ranking order (combined weighted score ranks the strongest memory first)
* importance weighting (importance-only ranking orders by importance column)
* recency weighting (recency-only ranking orders by created_at decay)
* semantic weighting (semantic-only ranking orders by cosine similarity)
* configurable weights (changing weights flips the ordering of candidates)
* tenant isolation (ranking never crosses org boundaries)
* regression safety (semantic retrieval / CRUD / conversation memory / embeddings
  are untouched; ranking is a read-only score layer)

It reuses the test harness from ``test_long_term_memory`` / ``test_semantic_memory``
(DB-backed session + auth-registered orgs) so tenant isolation is exercised
against the real ``RepositoryFactory`` scoping, not a mock.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.all_models import Agent, Conversation, Memory
from app.repositories.tenant_repository import RepositoryFactory
from app.services.embeddings import LocalDeterministicEmbedder
from app.services.long_term_memory import LongTermMemoryService
from app.services.memory_ranking import (
    MemoryRanker,
    RankingConfig,
    RankingWeights,
    get_memory_ranker,
)

AUTH_PREFIX = "/api/v1/auth"
UTC = timezone.utc


# ---------------------------------------------------------------------------
# Fixtures (mirror test_semantic_memory.py / test_memory_consolidation.py)
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
            "email": f"rank-owner-{uuid.uuid4()}@example.com",
            "password": "TestPass#123",
            "full_name": "Rank Owner",
            "organization_name": f"Rank Org {uuid.uuid4()}",
            "organization_slug": f"rank-org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _create_agent(db_session, org_id):
    agent = Agent(
        organization_id=org_id,
        data={
            "name": "Rank Agent",
            "system_prompt": "You are a helpful assistant.",
            "public_id": f"rank-agent-{uuid.uuid4()}",
        },
    )
    agent.id = uuid.uuid4()
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


def _make_service(db_session, org_id) -> LongTermMemoryService:
    return LongTermMemoryService(db_session, org_id)


def _make_ranker(db_session, org_id) -> MemoryRanker:
    return MemoryRanker(db_session, org_id)


def _insert(
    repo, org_id, content, importance=0, created_at=None, embedding=None
):
    """Direct tenant-scoped insert with explicit control over ranking signals."""
    m = Memory(organization_id=org_id, content=content, importance=importance)
    if created_at is not None:
        m.created_at = created_at
    if embedding is not None:
        m.embedding = embedding
    return repo.create(m)


# ---------------------------------------------------------------------------
# Ranking order (combined default weights)
# ---------------------------------------------------------------------------


def test_ranking_order_strongest_memory_first(db_session, client):
    """With default weights the most relevant+important+recent memory ranks #1."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    strong = service.create_memory(
        content="The user loves pizza and Italian food.",
        importance=9,
    )
    weak = service.create_memory(
        content="The quarterly compliance deadline is unrelated to food.",
        importance=0,
    )

    ranked = service.rank_memories_scored("pizza and Italian cuisine")
    assert ranked
    # The strong memory (relevant, important) wins the combined score.
    assert ranked[0].memory.id == strong.id
    # The weakest memory is last.
    assert ranked[-1].memory.id == weak.id


def test_ranking_scores_in_unit_range(db_session, client):
    """Total + decomposed scores all live in [0, 1] (weight-normalized)."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    service.create_memory(content="The user loves pizza.", importance=5)

    ranked = service.rank_memories_scored("pizza")
    assert ranked
    for r in ranked:
        assert 0.0 <= r.score <= 1.0
        assert 0.0 <= r.semantic_score <= 1.0
        assert 0.0 <= r.importance_score <= 1.0
        assert 0.0 <= r.recency_score <= 1.0


def test_ranking_empty_returns_empty(db_session, client):
    """Ranking an empty tenant returns []."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    assert service.rank_memories("anything") == []
    assert service.rank_memories_scored("anything") == []


# ---------------------------------------------------------------------------
# Importance weighting
# ---------------------------------------------------------------------------


def test_importance_weighting_orders_by_importance(db_session, client):
    """Importance-only ranking orders by the importance column."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    repo = service.repository_factory.memories()

    # High-importance memory is OLDER (so recency would have ranked it lower if
    # it had any weight) -> proves importance-only ignores recency.
    old = datetime(2026, 1, 1, tzinfo=UTC)
    new = datetime(2026, 7, 15, tzinfo=UTC)
    high = _insert(repo, org_id, "Important but stale fact.", importance=9, created_at=old)
    low = _insert(repo, org_id, "Trivial but fresh fact.", importance=1, created_at=new)

    cfg = RankingConfig(weights=RankingWeights(semantic=0, importance=1, recency=0))
    ranked = service.rank_memories_scored("anything at all", config=cfg)
    assert ranked[0].memory.id == high.id
    assert ranked[-1].memory.id == low.id
    # And the winner genuinely scored higher on importance.
    assert ranked[0].importance_score > ranked[-1].importance_score


# ---------------------------------------------------------------------------
# Recency weighting
# ---------------------------------------------------------------------------


def test_recency_weighting_orders_by_created_at(db_session, client):
    """Recency-only ranking orders newer memories first via time-decay."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    repo = service.repository_factory.memories()

    now = datetime(2026, 7, 16, tzinfo=UTC)
    old = datetime(2026, 1, 1, tzinfo=UTC)   # ~196 days old -> recency ~0
    new = datetime(2026, 7, 15, tzinfo=UTC)  # 1 day old -> recency ~0.97

    # The newer memory is also LESS important and LESS semantically relevant,
    # proving recency-only ignores the other signals.
    m_old = _insert(repo, org_id, "Old stale fact about kites.", importance=0, created_at=old)
    m_new = _insert(repo, org_id, "Fresh fact about pizza.", importance=0, created_at=new)

    cfg = RankingConfig(weights=RankingWeights(semantic=0, importance=0, recency=1))
    ranked = service.rank_memories_scored("pizza", now=now, config=cfg)
    assert ranked[0].memory.id == m_new.id
    assert ranked[-1].memory.id == m_old.id
    # Recency signal decays with age, as configured.
    assert ranked[0].recency_score > ranked[-1].recency_score


def test_recency_half_life_is_configurable(db_session, client):
    """A short half-life makes older memories score far lower on recency."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    repo = service.repository_factory.memories()

    now = datetime(2026, 7, 16, tzinfo=UTC)
    old = datetime(2026, 1, 1, tzinfo=UTC)  # ~196 days old
    m_old = _insert(repo, org_id, "Old fact.", importance=0, created_at=old)

    long_hl = RankingConfig(
        weights=RankingWeights(semantic=0, importance=0, recency=1),
        recency_half_life_days=365.0,
    )
    short_hl = RankingConfig(
        weights=RankingWeights(semantic=0, importance=0, recency=1),
        recency_half_life_days=7.0,
    )
    r_long = service.rank_memories_scored("x", now=now, config=long_hl)[0]
    r_short = service.rank_memories_scored("x", now=now, config=short_hl)[0]
    # A 196-day-old memory: small penalty with a 1-year half-life, huge penalty
    # with a 1-week half-life.
    assert r_long.recency_score > r_short.recency_score


# ---------------------------------------------------------------------------
# Semantic weighting
# ---------------------------------------------------------------------------


def test_semantic_weighting_orders_by_similarity(db_session, client):
    """Semantic-only ranking orders by cosine similarity to the query."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    service.create_memory(content="The user loves pizza and Italian food.")
    service.create_memory(content="The user prefers tea over coffee.")
    service.create_memory(content="The project deadline is next Friday.")

    cfg = RankingConfig(weights=RankingWeights(semantic=1, importance=0, recency=0))
    ranked = service.rank_memories_scored(
        "pizza and Italian cuisine", config=cfg
    )
    assert ranked
    # Pizza memory is most similar; the unrelated deadline memory is least.
    assert "pizza" in ranked[0].memory.content
    assert "deadline" in ranked[-1].memory.content
    # Scores strictly descend.
    sem = [r.semantic_score for r in ranked]
    assert sem == sorted(sem, reverse=True)


def test_semantic_weighting_ignores_importance(db_session, client):
    """With semantic-only weights, importance does not affect ordering."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    # Highly relevant but importance 0; irrelevant but importance 10.
    rel = service.create_memory(content="The user loves pizza.", importance=0)
    irre = service.create_memory(
        content="The quarterly compliance deadline is unrelated to food.", importance=10
    )

    cfg = RankingConfig(weights=RankingWeights(semantic=1, importance=0, recency=0))
    ranked = service.rank_memories_scored("pizza", config=cfg)
    assert ranked[0].memory.id == rel.id
    assert ranked[-1].memory.id == irre.id


# ---------------------------------------------------------------------------
# Configurable weights (flip ordering)
# ---------------------------------------------------------------------------


def test_configurable_weights_flip_order(db_session, client):
    """The same candidates reorder when weights change (semantic vs importance)."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    # High semantic, low importance vs zero semantic, high importance.
    sem_high = service.create_memory(content="The user loves pizza.", importance=1)
    imp_high = service.create_memory(
        content="The quarterly compliance deadline is unrelated to food.", importance=10
    )

    semantic_cfg = RankingConfig(
        weights=RankingWeights(semantic=1, importance=0, recency=0)
    )
    importance_cfg = RankingConfig(
        weights=RankingWeights(semantic=0, importance=1, recency=0)
    )

    by_semantic = [r.memory.id for r in service.rank_memories_scored(
        "pizza", config=semantic_cfg
    )]
    by_importance = [r.memory.id for r in service.rank_memories_scored(
        "pizza", config=importance_cfg
    )]

    assert by_semantic[0] == sem_high.id
    assert by_importance[0] == imp_high.id
    # The ordering is genuinely reversed by the weight configuration.
    assert by_semantic[0] != by_importance[0]


# ---------------------------------------------------------------------------
# top_k
# ---------------------------------------------------------------------------


def test_ranking_respects_top_k(db_session, client):
    """top_k caps the number of ranked memories."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    for i in range(6):
        service.create_memory(content=f"Distinct memory {i} about unrelated topics.")

    cfg = RankingConfig(weights=RankingWeights(semantic=1, importance=0, recency=0))
    top2 = service.rank_memories("memory", top_k=2, config=cfg)
    assert len(top2) == 2

    all_results = service.rank_memories("memory", config=cfg)
    assert len(top2) <= len(all_results)


# ---------------------------------------------------------------------------
# Standalone ranker / factory
# ---------------------------------------------------------------------------


def test_standalone_ranker_orders_by_importance(db_session, client):
    """The decoupled MemoryRanker works without the service wrapper."""
    token, org_id = _register(client)
    ranker = _make_ranker(db_session, org_id)
    repo = ranker.repository_factory.memories()
    a = _insert(repo, org_id, "Fact A.", importance=3)
    b = _insert(repo, org_id, "Fact B.", importance=8)

    cfg = RankingConfig(weights=RankingWeights(semantic=0, importance=1, recency=0))
    ranked = ranker.rank_memories("anything", config=cfg)
    assert [m.id for m in ranked] == [b.id, a.id]


def test_ranker_factory_builds_scoped_instance(db_session, client):
    """DI factory builds a correctly scoped standalone ranker."""
    token, org_id = _register(client)
    ranker = get_memory_ranker(db_session, org_id)
    assert isinstance(ranker, MemoryRanker)
    assert ranker.organization_id == org_id


def test_ranker_accepts_precomputed_memories(db_session, client):
    """Chat/Orchestrator can pass an already-recalled list (e.g. semantic hits)."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    m1 = service.create_memory(content="The user loves pizza.", importance=2)
    m2 = service.create_memory(content="The user prefers tea.", importance=9)

    ranker = _make_ranker(db_session, org_id)
    cfg = RankingConfig(weights=RankingWeights(semantic=0, importance=1, recency=0))
    # Pass the explicit list rather than letting the ranker fetch its own.
    ranked = ranker.rank_memories(
        "ignored", memories=[m1, m2], config=cfg
    )
    assert [m.id for m in ranked] == [m2.id, m1.id]


# ---------------------------------------------------------------------------
# format_for_prompt (reuse helper for Chat / Orchestrator / Router)
# ---------------------------------------------------------------------------


def test_format_for_prompt_renders_ranked_memories(db_session, client):
    """format_for_prompt renders ranked memories in ranking order."""
    token, org_id = _register(client)
    ranker = _make_ranker(db_session, org_id)
    repo = ranker.repository_factory.memories()
    hi = _insert(repo, org_id, "High importance fact.", importance=9)
    lo = _insert(repo, org_id, "Low importance fact.", importance=1)

    cfg = RankingConfig(weights=RankingWeights(semantic=0, importance=1, recency=0))
    ranked = ranker.rank("anything", config=cfg)
    block = ranker.format_for_prompt(ranked)
    assert "High importance fact." in block
    assert "Low importance fact." in block
    # Highest-ranked (importance 9) appears first in the block.
    assert block.index("High importance fact.") < block.index("Low importance fact.")


def test_format_for_prompt_empty(db_session, client):
    """Empty input yields an empty string so callers can skip injection."""
    token, org_id = _register(client)
    ranker = _make_ranker(db_session, org_id)
    assert ranker.format_for_prompt([]) == ""


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_tenant_isolation_ranking_scoped(db_session, client):
    """Ranking never crosses tenant boundaries."""
    token_a, org_a = _register(client)
    token_b, org_b = _register(client)

    service_a = _make_service(db_session, org_a)
    service_b = _make_service(db_session, org_b)

    # Identical content + importance in both tenants.
    mem_a = service_a.create_memory(
        content="The user loves pizza and Italian food.", importance=9
    )
    mem_b = service_b.create_memory(
        content="The user loves pizza and Italian food.", importance=9
    )

    # Org B's ranking must surface ONLY Org B's memory at #1.
    ranked_b = service_b.rank_memories_scored("user loves pizza and Italian food")
    assert ranked_b
    assert all(str(m.memory.organization_id) == org_b for m in ranked_b)
    assert ranked_b[0].memory.id == mem_b.id
    # Critically, Org A's memory is never returned to Org B.
    assert mem_a.id not in {m.memory.id for m in ranked_b}

    # Symmetric for Org A.
    ranked_a = service_a.rank_memories_scored("user loves pizza and Italian food")
    assert all(str(m.memory.organization_id) == org_a for m in ranked_a)
    assert ranked_a[0].memory.id == mem_a.id
    assert mem_b.id not in {m.memory.id for m in ranked_a}


def test_tenant_isolation_standalone_ranker(db_session, client):
    """The standalone ranker is also tenant-scoped via RepositoryFactory."""
    token_a, org_a = _register(client)
    token_b, org_b = _register(client)

    ranker_a = _make_ranker(db_session, org_a)
    ranker_b = _make_ranker(db_session, org_b)
    embedder = LocalDeterministicEmbedder()

    mem_a = Memory(organization_id=org_a, content="Org A confidential fact.")
    mem_a.embedding = embedder.embed([mem_a.content])[0]
    ranker_a.repository_factory.memories().create(mem_a)

    mem_b = Memory(organization_id=org_b, content="Org B confidential fact.")
    mem_b.embedding = embedder.embed([mem_b.content])[0]
    ranker_b.repository_factory.memories().create(mem_b)

    cfg = RankingConfig(weights=RankingWeights(semantic=1, importance=0, recency=0))
    out_b = ranker_b.rank_memories("confidential fact", config=cfg)
    assert all(str(m.organization_id) == org_b for m in out_b)
    assert mem_b.id in {m.id for m in out_b}
    assert mem_a.id not in {m.id for m in out_b}


# ---------------------------------------------------------------------------
# Regression safety
# ---------------------------------------------------------------------------


def test_regression_existing_crud_unaffected(db_session, client):
    """Adding ranking does not change CRUD / keyword behavior."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    m1 = service.create_memory(
        content="The user dislikes cold emails.", category="preference", key="email_pref", importance=4
    )
    # Keyword search still works (non-semantic path untouched).
    hits = service.search_by_content("cold")
    assert len(hits) == 1 and "cold" in hits[0].content

    # Ranking runs without mutating anything.
    service.rank_memories_scored("cold")
    assert service.count() == 1
    assert service.get_by_key("email_pref").id == m1.id

    # CRUD still works.
    service.update_memory(m1.id, content="The user dislikes spam emails.")
    assert "spam" in service.get_memory(m1.id).content
    assert service.delete_memory(m1.id) is True
    assert service.count() == 0


def test_regression_embedding_populated_on_write(db_session, client):
    """Memories still carry a populated embedding after ranking added."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    mem = service.create_memory(content="The user loves pizza.", importance=3)
    assert mem.embedding is not None and len(mem.embedding) > 0
    # Ranking does not strip the embedding.
    service.rank_memories("pizza")
    assert service.get_memory(mem.id).embedding is not None
    service.delete_memory(mem.id)


def test_regression_semantic_retrieval_untouched(db_session, client):
    """Ranking leaves semantic retrieval working and tenant-scoped."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    service.create_memory(content="The user loves pizza and Italian food.", category="preference", importance=7)
    service.create_memory(content="The user prefers tea over coffee.", category="preference", importance=2)

    ranked = service.rank_memories_scored("pizza and Italian cuisine")
    assert ranked and "pizza" in ranked[0].memory.content

    # The dedicated semantic retrieval path is independent and still correct.
    sem = service.retrieve_semantic("pizza and Italian cuisine")
    assert sem and "pizza" in sem[0].content
    assert all(str(m.organization_id) == org_id for m in sem)


def test_regression_conversation_memory_untouched(db_session, client):
    """Ranking is independent of Conversation Memory logic."""
    from app.services.conversation_memory import ConversationMemoryService

    token, org_id = _register(client)
    repo_factory = RepositoryFactory(db_session, org_id)
    agent = _create_agent(db_session, org_id)
    conv = Conversation(
        organization_id=org_id,
        agent_id=agent.id,
        session_id=f"rank-sess-{uuid.uuid4()}",
    )
    conv.id = uuid.uuid4()
    repo_factory.conversations().create(conv)
    service = _make_service(db_session, org_id)
    service.create_memory(content="The user loves pizza.", importance=5)

    cm = ConversationMemoryService(db_session, org_id)
    # Ranking runs without disturbing ConversationMemoryService.
    ranked = service.rank_memories_scored("pizza")
    assert ranked

    # Conversation memory still functions normally afterwards.
    ctx, _, _ = cm.build_context(conv.id, "ignored query")
    assert ctx is not None

    repo_factory.conversations().delete(conv)
    db_session.delete(agent)
    db_session.commit()


def test_regression_ranking_does_not_mutate_importance(db_session, client):
    """Ranking is read-only: importance values are preserved afterward."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    m = service.create_memory(content="The user loves pizza.", importance=6)

    service.rank_memories_scored("pizza")
    assert service.get_memory(m.id).importance == 6
    assert service.count() == 1


def test_regression_agent_scoped_ranking(db_session, client):
    """Ranking can be scoped to an agent without breaking isolation."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    agent = _create_agent(db_session, org_id)

    service.create_memory(content="The user loves pizza.", agent_id=agent.id, importance=8)
    service.create_memory(content="The user prefers tea.", importance=1)

    cfg = RankingConfig(weights=RankingWeights(semantic=0, importance=1, recency=0))
    scoped = service.rank_memories("pizza", agent_id=agent.id, config=cfg)
    assert len(scoped) == 1
    assert scoped[0].agent_id == agent.id

    all_results = service.rank_memories("preferences", config=cfg)
    assert len(all_results) == 2

    service.delete_memory(scoped[0].id)
    other = service.list_memories()[0]
    service.delete_memory(other.id)
    db_session.delete(agent)
    db_session.commit()
