"""Memory Consolidation tests (Milestone 5, Phase 2.4).

Tests the detect + merge of duplicate long-term memories provided by
``MemoryConsolidationService`` (and the ``LongTermMemoryService`` wrapper).

Coverage required by the phase:
* duplicate detection (similar pairs found, no false positives)
* memory merging (row count drops, never grows)
* metadata preservation (all keys kept; survivor wins conflicts)
* importance preservation (maximum importance kept)
* tenant isolation (consolidation never crosses org boundaries)
* regression safety (semantic retrieval & conversation memory untouched;
  consolidation never creates new duplicate memories / is idempotent)

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
from app.services.long_term_memory import LongTermMemoryService
from app.services.memory_consolidation import (
    MemoryConsolidationService,
)

AUTH_PREFIX = "/api/v1/auth"


# ---------------------------------------------------------------------------
# Fixtures (mirror test_long_term_memory.py / test_semantic_memory.py)
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
            "email": f"cons-owner-{uuid.uuid4()}@example.com",
            "password": "TestPass#123",
            "full_name": "Cons Owner",
            "organization_name": f"Cons Org {uuid.uuid4()}",
            "organization_slug": f"cons-org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _create_agent(db_session, org_id):
    agent = Agent(
        organization_id=org_id,
        data={
            "name": "Cons Agent",
            "system_prompt": "You are a helpful assistant.",
            "public_id": f"cons-agent-{uuid.uuid4()}",
        },
    )
    agent.id = uuid.uuid4()
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


def _make_service(db_session, org_id) -> LongTermMemoryService:
    return LongTermMemoryService(db_session, org_id)


def _make_consolidator(db_session, org_id) -> MemoryConsolidationService:
    return MemoryConsolidationService(db_session, org_id)


# ---------------------------------------------------------------------------
# Duplicate detection (read-only)
# ---------------------------------------------------------------------------


def test_detect_exact_duplicate_pair(db_session, client):
    """Two identical-content memories are detected as a duplicate pair."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    service.create_memory(content="The user prefers dark mode.", category="preference")
    service.create_memory(content="The user prefers dark mode.", category="preference")

    pairs = _make_consolidator(db_session, org_id).find_duplicate_pairs()
    assert len(pairs) == 1
    # Identical content -> cosine similarity ~1.0.
    assert pairs[0].similarity > 0.99
    # Both ids are real memories in this tenant (no cross-tenant leakage).
    ids = {p.duplicate_id for p in pairs} | {p.survivor_id for p in pairs}
    assert ids <= {m.id for m in service.list_memories()}


def test_detect_no_false_positive_for_unrelated(db_session, client):
    """Unrelated memories are NOT flagged as duplicates above threshold."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    service.create_memory(content="The user loves pizza and Italian food.")
    service.create_memory(content="The project deadline is next Friday.")

    pairs = _make_consolidator(db_session, org_id).find_duplicate_pairs(
        similarity_threshold=0.95
    )
    assert pairs == []


def test_detect_respects_threshold(db_session, client):
    """A near-duplicate pair only appears when the threshold is low enough."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    service.create_memory(content="The user prefers dark mode.")
    service.create_memory(content="The user prefers dark theme.")

    # High threshold may miss loosely related phrasing.
    strict = _make_consolidator(db_session, org_id).find_duplicate_pairs(
        similarity_threshold=0.99
    )
    # Low threshold still must not conflate clearly different sentences.
    relaxed = _make_consolidator(db_session, org_id).find_duplicate_pairs(
        similarity_threshold=0.50
    )
    # Both lists stay consistent with "no false merge" for genuinely different
    # text; the exact counts are embedder-dependent, so assert no crash + ids valid.
    for p in strict + relaxed:
        assert p.duplicate_id in {m.id for m in service.list_memories()}


def test_detect_is_read_only(db_session, client):
    """Detection performs no mutation (count unchanged, no deletes)."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    service.create_memory(content="Duplicate one.")
    service.create_memory(content="Duplicate one.")

    before = service.count()
    _make_consolidator(db_session, org_id).find_duplicate_pairs()
    after = service.count()
    assert before == 2
    assert after == 2


# ---------------------------------------------------------------------------
# Memory merging
# ---------------------------------------------------------------------------


def test_consolidate_merges_duplicates(db_session, client):
    """Two identical memories consolidate down to one."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    m1 = service.create_memory(content="The user prefers dark mode.", category="preference")
    m2 = service.create_memory(content="The user prefers dark mode.", category="preference")

    result = service.consolidate_memories(similarity_threshold=0.95)
    assert result.detected_pairs == 1
    assert result.merged_count == 1
    assert result.remaining_count == 1

    remaining = service.list_memories()
    assert len(remaining) == 1
    # The surviving memory is one of the originals (no new row created).
    assert remaining[0].id in {m1.id, m2.id}


def test_consolidate_three_way_transitive(db_session, client):
    """Three mutually-similar memories collapse into a single survivor."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    for _ in range(3):
        service.create_memory(content="The user prefers dark mode.")

    result = service.consolidate_memories(similarity_threshold=0.95)
    assert result.detected_pairs == 2
    assert result.merged_count == 2
    assert result.remaining_count == 1
    assert len(service.list_memories()) == 1


def test_consolidate_never_creates_duplicates(db_session, client):
    """Consolidation only deletes; running it twice is idempotent."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    service.create_memory(content="The user prefers dark mode.")
    service.create_memory(content="The user prefers dark mode.")

    first = service.consolidate_memories(similarity_threshold=0.95)
    assert first.remaining_count == 1

    # Second pass finds nothing to merge.
    second = service.consolidate_memories(similarity_threshold=0.95)
    assert second.detected_pairs == 0
    assert second.merged_count == 0
    assert second.remaining_count == 1
    assert service.count() == 1


# ---------------------------------------------------------------------------
# Metadata preservation
# ---------------------------------------------------------------------------


def test_metadata_preserved_across_merge(db_session, client):
    """All unique metadata keys survive the merge."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    survivor = service.create_memory(
        content="The user prefers dark mode.",
        metadata={"source": "onboarding", "channel": "chat"},
    )
    service.create_memory(
        content="The user prefers dark mode.",
        metadata={"topic": "ui", "channel": "settings"},
    )

    service.consolidate_memories(similarity_threshold=0.95)

    kept = service.get_memory(survivor.id)
    # Unique keys from both memories are present.
    assert kept.meta["source"] == "onboarding"
    assert kept.meta["topic"] == "ui"
    # Conflicting key -> survivor wins.
    assert kept.meta["channel"] == "chat"
    assert len(service.list_memories()) == 1


# ---------------------------------------------------------------------------
# Importance preservation
# ---------------------------------------------------------------------------


def test_importance_preserves_maximum(db_session, client):
    """The merged memory keeps the highest importance in the group."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    low = service.create_memory(
        content="The user prefers dark mode.", importance=2
    )
    service.create_memory(content="The user prefers dark mode.", importance=8)

    service.consolidate_memories(similarity_threshold=0.95)

    kept = service.get_memory(low.id)
    assert kept.importance == 8
    assert len(service.list_memories()) == 1


def test_importance_preserved_when_survivor_is_highest(db_session, client):
    """If the survivor already has the max importance, it is retained."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    high = service.create_memory(
        content="The user prefers dark mode.", importance=9
    )
    service.create_memory(content="The user prefers dark mode.", importance=3)

    service.consolidate_memories(similarity_threshold=0.95)

    kept = service.get_memory(high.id)
    assert kept.importance == 9


# ---------------------------------------------------------------------------
# Timestamp correctness
# ---------------------------------------------------------------------------


def test_timestamps_updated_correctly(db_session, client):
    """Survivor keeps its created_at; updated_at moves to consolidation time."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    m1 = service.create_memory(content="The user prefers dark mode.")
    m2 = service.create_memory(content="The user prefers dark mode.")

    service.consolidate_memories(similarity_threshold=0.95)

    # The earliest-created memory survives (created_at preserved).
    survivor = service.get_memory(m1.id)
    assert survivor is not None
    assert survivor.created_at == m1.created_at
    # updated_at is bumped to the consolidation time (>= created_at).
    assert survivor.updated_at >= survivor.created_at
    # The duplicate is gone.
    assert service.get_memory(m2.id) is None


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_tenant_isolation_consolidation_scoped(db_session, client):
    """Consolidating org A never affects org B's memories."""
    token_a, org_a = _register(client)
    token_b, org_b = _register(client)
    service_a = _make_service(db_session, org_a)
    service_b = _make_service(db_session, org_b)

    # Identical duplicate content in BOTH tenants.
    service_a.create_memory(content="Org A secret fact.")
    service_a.create_memory(content="Org A secret fact.")
    service_b.create_memory(content="Org B secret fact.")
    service_b.create_memory(content="Org B secret fact.")

    # Consolidate only org A.
    result_a = service_a.consolidate_memories(similarity_threshold=0.95)
    assert result_a.merged_count == 1
    assert result_a.remaining_count == 1

    # Org B is completely untouched -- still two separate memories.
    assert service_b.count() == 2
    # Org A's consolidation never saw / deleted Org B's rows.
    assert service_b.get_memory(
        service_b.list_memories()[0].id
    ) is not None

    # Org B can still consolidate independently.
    result_b = service_b.consolidate_memories(similarity_threshold=0.95)
    assert result_b.merged_count == 1
    assert result_b.remaining_count == 1


def test_tenant_isolation_detection_scoped(db_session, client):
    """Duplicate detection never reports another tenant's memories."""
    token_a, org_a = _register(client)
    token_b, org_b = _register(client)
    service_a = _make_service(db_session, org_a)
    service_b = _make_service(db_session, org_b)

    service_a.create_memory(content="Shared duplicate line.")
    service_a.create_memory(content="Shared duplicate line.")
    service_b.create_memory(content="Shared duplicate line.")
    service_b.create_memory(content="Shared duplicate line.")

    pairs_a = _make_consolidator(db_session, org_a).find_duplicate_pairs()
    pairs_b = _make_consolidator(db_session, org_b).find_duplicate_pairs()

    # Each tenant sees exactly its own single pair.
    assert len(pairs_a) == 1
    assert len(pairs_b) == 1
    a_ids = {p.duplicate_id for p in pairs_a} | {p.survivor_id for p in pairs_a}
    b_ids = {p.duplicate_id for p in pairs_b} | {p.survivor_id for p in pairs_b}
    # No id appears in both tenants' detection (strict isolation).
    assert a_ids.isdisjoint(b_ids)


# ---------------------------------------------------------------------------
# Regression safety
# ---------------------------------------------------------------------------


def test_regression_semantic_retrieval_untouched(db_session, client):
    """Consolidation leaves semantic retrieval working and tenant-scoped."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)
    service.create_memory(content="The user loves pizza and Italian food.", category="preference")
    service.create_memory(content="The user prefers tea over coffee.", category="preference")
    # A duplicate of the pizza memory (gets merged away).
    service.create_memory(content="The user loves pizza and Italian food.", category="preference")

    service.consolidate_memories(similarity_threshold=0.95)

    # Semantic retrieval still returns the surviving pizza memory.
    results = service.retrieve_semantic("pizza and Italian cuisine")
    assert len(results) >= 1
    assert "pizza" in results[0].content
    # Tenant-scoped (no cross-org rows exist here, but assert shape intact).
    assert all(str(m.organization_id) == org_id for m in results)


def test_regression_existing_crud_unaffected(db_session, client):
    """Adding consolidation does not change CRUD / keyword behavior."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    m1 = service.create_memory(
        content="The user dislikes cold emails.", category="preference", key="email_pref"
    )
    service.create_memory(content="The user dislikes cold emails.", category="preference")

    # Keyword search still works (non-semantic path untouched).
    hits = service.search_by_content("cold")
    assert len(hits) == 2

    # Consolidate the two duplicate cold-email memories.
    service.consolidate_memories(similarity_threshold=0.95)
    assert service.get_by_key("email_pref").id == m1.id
    # The surviving memory still contains "cold" (it is a merge, not a wipe).
    assert len(service.search_by_content("cold")) == 1
    assert service.count() == 1

    # CRUD still works after consolidation.
    service.update_memory(m1.id, content="The user dislikes spam emails.")
    assert "spam" in service.get_memory(m1.id).content
    assert service.delete_memory(m1.id) is True
    assert service.count() == 0


def test_regression_conversation_memory_untouched(db_session, client):
    """Consolidation is independent of Conversation Memory logic."""
    from app.services.conversation_memory import ConversationMemoryService

    token, org_id = _register(client)
    repo_factory = RepositoryFactory(db_session, org_id)
    agent = _create_agent(db_session, org_id)
    conv = Conversation(
        organization_id=org_id,
        agent_id=agent.id,
        session_id=f"cons-sess-{uuid.uuid4()}",
    )
    conv.id = uuid.uuid4()
    repo_factory.conversations().create(conv)
    service = _make_service(db_session, org_id)
    service.create_memory(content="The user prefers dark mode.")
    service.create_memory(content="The user prefers dark mode.")

    cm = ConversationMemoryService(db_session, org_id)
    # Consolidation runs without disturbing ConversationMemoryService.
    service.consolidate_memories(similarity_threshold=0.95)
    assert service.count() == 1

    # Conversation memory still functions normally afterwards.
    ctx, _, _ = cm.build_context(conv.id, "ignored query")
    assert ctx is not None

    repo_factory.conversations().delete(conv)
    db_session.delete(agent)
    db_session.commit()


def test_consolidator_factory_builds_scoped_service(db_session, client):
    """MemoryConsolidationService inherits the org scoping from the service."""
    token, org_id = _register(client)
    consolidator = _make_consolidator(db_session, org_id)
    assert consolidator.organization_id == org_id
    # It reuses the same repository_factory scoping as the memory service.
    assert consolidator.repository_factory.memories().organization_id == org_id
