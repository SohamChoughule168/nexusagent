"""Long-Term Memory Store tests (Milestone 5, Phase 2.2).

Tests the four CRUD deliverables plus retrieval, tenant isolation, repository
reuse, and regression safety of ``LongTermMemoryService`` / ``MemoryRepository``.

Non-semantic retrieval only (key / category / keyword). Semantic retrieval
(``embedding``), importance ranking, and consolidation are explicitly deferred
to later phases; their columns exist but are not exercised for retrieval here.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.all_models import Agent, Memory, OrganizationMember
from app.repositories.tenant_repository import RepositoryFactory
from app.services.long_term_memory import (
    LongTermMemoryService,
    get_long_term_memory_service,
)

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
    email = f"ltm-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "LTM Owner",
            "organization_name": f"LTM Org {uuid.uuid4()}",
            "organization_slug": f"ltm-org-{uuid.uuid4()}",
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
            "name": "LTM Agent",
            "system_prompt": "You are a helpful assistant.",
            "public_id": f"ltm-agent-{uuid.uuid4()}",
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
# Create
# ---------------------------------------------------------------------------


def test_create_memory_basic(db_session, client):
    """A memory is persisted and tenant-scoped to the organization."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    mem = service.create_memory(content="The user prefers dark mode.")
    assert mem.id is not None
    # organization_id is stored as a UUID on the ORM model (as_uuid=True), while
    # the API/registration returns it as a string -- compare canonically.
    assert str(mem.organization_id) == org_id
    assert mem.content == "The user prefers dark mode."
    # Vector-store architecture reuse: embedding populated at write time.
    assert mem.embedding is not None and len(mem.embedding) > 0

    # It is retrievable via its own ID.
    fetched = service.get_memory(mem.id)
    assert fetched is not None
    assert fetched.id == mem.id

    # Cleanup
    service.delete_memory(mem.id)


def test_create_memory_with_all_fields(db_session, client):
    """All optional fields (category, key, importance, metadata) are stored."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    service = _make_service(db_session, org_id)

    mem = service.create_memory(
        content="Project codename is Nebula.",
        category="fact",
        key="project_codename",
        importance=5,
        agent_id=agent.id,
        metadata={"source": "onboarding"},
    )
    assert mem.category == "fact"
    assert mem.key == "project_codename"
    assert mem.importance == 5
    assert mem.agent_id == agent.id
    assert mem.meta == {"source": "onboarding"}

    service.delete_memory(mem.id)
    db_session.delete(agent)
    db_session.commit()


def test_create_memory_empty_content_raises(db_session, client):
    """Empty content is rejected."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    with pytest.raises(ValueError):
        service.create_memory(content="   ")


def test_create_memory_duplicate_key_raises(db_session, client):
    """A duplicate per-tenant key is rejected."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    m1 = service.create_memory(content="First", key="dup")
    with pytest.raises(ValueError):
        service.create_memory(content="Second", key="dup")

    service.delete_memory(m1.id)


# ---------------------------------------------------------------------------
# Read / retrieve (non-semantic)
# ---------------------------------------------------------------------------


def test_get_memory_returns_none_for_missing(db_session, client):
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    assert service.get_memory(uuid.uuid4()) is None


def test_get_by_key(db_session, client):
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    service.create_memory(content="Prefers async standups.", key="standup_style", category="preference")
    found = service.get_by_key("standup_style")
    assert found is not None
    assert found.content == "Prefers async standups."

    assert service.get_by_key("missing-key") is None


def test_list_memories_empty(db_session, client):
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    assert service.list_memories() == []


def test_list_memories_and_category_filter(db_session, client):
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    service.create_memory(content="Fact A", category="fact")
    service.create_memory(content="Pref B", category="preference")
    service.create_memory(content="Fact C", category="fact")

    all_mem = service.list_memories()
    assert len(all_mem) == 3

    facts = service.list_memories(category="fact")
    assert len(facts) == 2
    assert {m.content for m in facts} == {"Fact A", "Fact C"}

    prefs = service.get_by_category("preference")
    assert len(prefs) == 1
    assert prefs[0].content == "Pref B"


def test_search_by_content_keyword(db_session, client):
    """Keyword search is case-insensitive substring match (non-semantic)."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    service.create_memory(content="User dislikes cold emails.")
    service.create_memory(content="User loves warm intros.")
    service.create_memory(content="Competitor is Acme Corp.")

    hits = service.search_by_content("cold")
    assert len(hits) == 1
    assert "cold" in hits[0].content

    # Case-insensitive.
    hits_ci = service.search_by_content("COLD")
    assert len(hits_ci) == 1

    # No match -> empty.
    assert service.search_by_content("zzz-not-present") == []


def test_count(db_session, client):
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    assert service.count() == 0
    m1 = service.create_memory(content="One")
    m2 = service.create_memory(content="Two")
    assert service.count() == 2

    service.delete_memory(m1.id)
    service.delete_memory(m2.id)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_memory_content_and_embedding(db_session, client):
    """Updating content republishes the embedding and the new text."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    mem = service.create_memory(content="Old fact.")
    old_embedding = list(mem.embedding)

    updated = service.update_memory(mem.id, content="New fact.")
    assert updated is not None
    assert updated.content == "New fact."
    assert updated.embedding is not None
    assert updated.embedding != old_embedding

    service.delete_memory(mem.id)


def test_update_memory_partial_fields(db_session, client):
    """Only provided fields are changed."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    mem = service.create_memory(content="C", category="fact", importance=1)
    updated = service.update_memory(mem.id, category="preference", importance=9)

    assert updated.content == "C"
    assert updated.category == "preference"
    assert updated.importance == 9

    service.delete_memory(mem.id)


def test_update_memory_rekey_collision(db_session, client):
    """Rekeying onto another memory's key is rejected."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    m1 = service.create_memory(content="A", key="k1")
    m2 = service.create_memory(content="B", key="k2")
    with pytest.raises(ValueError):
        service.update_memory(m2.id, key="k1")

    service.delete_memory(m1.id)
    service.delete_memory(m2.id)


def test_update_memory_empty_content_raises(db_session, client):
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    mem = service.create_memory(content="C")
    with pytest.raises(ValueError):
        service.update_memory(mem.id, content="  ")

    service.delete_memory(mem.id)


def test_update_missing_memory_returns_none(db_session, client):
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    assert service.update_memory(uuid.uuid4(), content="x") is None


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_memory(db_session, client):
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    mem = service.create_memory(content="To delete")
    assert service.delete_memory(mem.id) is True
    assert service.get_memory(mem.id) is None
    assert service.count() == 0


def test_delete_missing_memory_returns_false(db_session, client):
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    assert service.delete_memory(uuid.uuid4()) is False


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_tenant_isolation_no_cross_org_visibility(db_session, client):
    """Memories from org A are never visible to org B (and vice versa)."""
    token_a, org_a = _register(client)
    token_b, org_b = _register(client)

    service_a = _make_service(db_session, org_a)
    service_b = _make_service(db_session, org_b)

    mem_a = service_a.create_memory(
        content="Org A secret fact.", key="secret", category="fact"
    )
    # Org B writes its own memory with the *same key* (allowed: keys are
    # per-tenant, so no collision across orgs).
    mem_b = service_b.create_memory(
        content="Org B secret fact.", key="secret", category="fact"
    )

    # Each service only sees its own tenant's memory.
    assert len(service_a.list_memories()) == 1
    assert len(service_b.list_memories()) == 1

    # Org B cannot fetch Org A's memory by ID (tenant-filtered).
    assert service_b.get_memory(mem_a.id) is None
    # Org B cannot fetch Org A's memory by key.
    assert service_b.get_by_key("secret").id == mem_b.id
    assert service_a.get_by_key("secret").id == mem_a.id

    # Counts are per-tenant.
    assert service_a.count() == 1
    assert service_b.count() == 1

    service_a.delete_memory(mem_a.id)
    service_b.delete_memory(mem_b.id)


def test_tenant_isolation_delete_is_scoped(db_session, client):
    """Deleting within org A does not remove org B's memory."""
    token_a, org_a = _register(client)
    token_b, org_b = _register(client)

    service_a = _make_service(db_session, org_a)
    service_b = _make_service(db_session, org_b)

    mem_a = service_a.create_memory(content="A only")
    mem_b = service_b.create_memory(content="B only")

    # Org B cannot delete Org A's memory (returns False, no-op).
    assert service_b.delete_memory(mem_a.id) is False
    assert service_a.get_memory(mem_a.id) is not None

    service_a.delete_memory(mem_a.id)
    service_b.delete_memory(mem_b.id)


def test_tenant_isolation_repository_under_service(db_session, client):
    """The service's repository is wired to the service's organization."""
    token, org_id = _register(client)
    service = _make_service(db_session, org_id)

    repo = service.repository_factory.memories()
    assert repo.organization_id == org_id

    # RepositoryFactory for the same org produces the same scoping.
    factory = RepositoryFactory(db_session, org_id)
    assert factory.memories().organization_id == org_id


# ---------------------------------------------------------------------------
# Repository reuse / regression safety
# ---------------------------------------------------------------------------


def test_repository_factory_reuses_existing_patterns(db_session, client):
    """MemoryRepository composes with the rest of the factory (no duplication)."""
    token, org_id = _register(client)
    factory = RepositoryFactory(db_session, org_id)

    # Same organization scoping as every other tenant-aware repository.
    assert factory.memories().organization_id == factory.agents().organization_id

    mem = factory.memories().create(
        Memory(organization_id=org_id, content="Reused repo path")
    )
    assert mem.id is not None
    assert factory.memories().count() == 1

    factory.memories().delete(mem)


def test_existing_models_unaffected_by_new_table(db_session, client):
    """Adding the memories table/CRUD does not break existing agent storage."""
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)

    # Pre-existing repositories still work.
    factory = RepositoryFactory(db_session, org_id)
    assert factory.agents().get(agent.id) is not None

    # Memory CRUD coexists.
    service = _make_service(db_session, org_id)
    mem = service.create_memory(content="Coexists with agents")
    assert service.count() == 1

    service.delete_memory(mem.id)
    db_session.delete(agent)
    db_session.commit()


def test_factory_function_builds_scoped_service(db_session, client):
    """The DI factory builds a correctly scoped service."""
    token, org_id = _register(client)
    service = get_long_term_memory_service(db_session, org_id)

    assert isinstance(service, LongTermMemoryService)
    assert service.organization_id == org_id
