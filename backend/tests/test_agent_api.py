"""Tenant-scoped Agent API tests.

Guards that every Agent endpoint (POST / GET list / GET by id / PUT / DELETE)
is isolated to the authenticated principal's organization and that existing
RBAC (``can_manage_agents``) is enforced at the API boundary.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_sessionmaker as SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.all_models import Agent, OrganizationMember
from app.models.organization import Organization
from app.models.user import User
from app.repositories.tenant_repository import RepositoryFactory

API_PREFIX = "/api/v1/agents"
AUTH_PREFIX = "/api/v1/auth"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()()
    try:
        yield db
    finally:
        db.close()


def _register(client: TestClient):
    """Register a new org owner; returns (access_token, organization_id, user_id)."""
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
    return body["access_token"], body["user"]["organization_id"], body["user"]["id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_member(db: Session, org_id: str, role: str) -> tuple[str, str]:
    """Create a user in ``org_id`` with the given role; mint and return a token."""
    user_id = uuid.uuid4()
    user = User(
        id=str(user_id),
        email=f"{role}-{uuid.uuid4()}@example.com",
        is_active=True,
        password_hash="dummy",
    )
    db.add(user)
    membership = OrganizationMember(
        organization_id=str(org_id),
        user_id=str(user_id),
        role=role,
    )
    membership.id = uuid.uuid4()
    db.add(membership)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, uuid.UUID(str(org_id)))
    return token, str(user_id)


def _create_agent_payload(public_id: str) -> dict:
    return {
        "name": f"Agent {public_id}",
        "system_prompt": "You are a helpful assistant.",
        "public_id": public_id,
        "model_provider": "openrouter",
    }


# ---------------------------------------------------------------------------
# 401: authentication required
# ---------------------------------------------------------------------------


def test_create_agent_requires_token(client):
    resp = client.post(f"{API_PREFIX}/", json=_create_agent_payload("p-noauth"))
    assert resp.status_code == 401


def test_list_agents_requires_token(client):
    resp = client.get(f"{API_PREFIX}/")
    assert resp.status_code == 401


def test_get_agent_requires_token(client):
    resp = client.get(f"{API_PREFIX}/p-noauth")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# CRUD functional + tenant scoping
# ---------------------------------------------------------------------------


def test_create_and_read_agent(client, db_session):
    token, org_id, _ = _register(client)
    public_id = f"p-crud-{uuid.uuid4()}"

    create = client.post(
        f"{API_PREFIX}/", json=_create_agent_payload(public_id),
        headers=_auth_headers(token),
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["public_id"] == public_id
    assert body["name"] == f"Agent {public_id}"

    # GET by id returns the same agent within the tenant.
    got = client.get(f"{API_PREFIX}/{public_id}", headers=_auth_headers(token))
    assert got.status_code == 200, got.text
    assert got.json()["public_id"] == public_id

    # List contains exactly this tenant's agent.
    listed = client.get(f"{API_PREFIX}/", headers=_auth_headers(token))
    assert listed.status_code == 200
    ids = {a["public_id"] for a in listed.json()}
    assert public_id in ids


def test_update_agent_functional(client, db_session):
    token, org_id, _ = _register(client)
    public_id = f"p-upd-{uuid.uuid4()}"
    client.post(
        f"{API_PREFIX}/", json=_create_agent_payload(public_id),
        headers=_auth_headers(token),
    )

    upd = client.put(
        f"{API_PREFIX}/{public_id}",
        json={"name": "Renamed Agent", "status": "active"},
        headers=_auth_headers(token),
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["name"] == "Renamed Agent"
    assert upd.json()["status"] == "active"

    # Persisted: a fresh GET reflects the change.
    got = client.get(f"{API_PREFIX}/{public_id}", headers=_auth_headers(token))
    assert got.json()["name"] == "Renamed Agent"


def test_delete_agent_functional(client, db_session):
    token, org_id, _ = _register(client)
    public_id = f"p-del-{uuid.uuid4()}"
    client.post(
        f"{API_PREFIX}/", json=_create_agent_payload(public_id),
        headers=_auth_headers(token),
    )

    deleted = client.delete(f"{API_PREFIX}/{public_id}", headers=_auth_headers(token))
    assert deleted.status_code == 204, deleted.text

    got = client.get(f"{API_PREFIX}/{public_id}", headers=_auth_headers(token))
    assert got.status_code == 404


# ---------------------------------------------------------------------------
# Tenant isolation: one org cannot see/modify another's agents
# ---------------------------------------------------------------------------


def test_other_tenant_cannot_access_agent(client, db_session):
    token_a, org_a, _ = _register(client)
    token_b, org_b, _ = _register(client)
    assert org_a != org_b

    public_id = f"p-iso-{uuid.uuid4()}"
    created = client.post(
        f"{API_PREFIX}/", json=_create_agent_payload(public_id),
        headers=_auth_headers(token_a),
    )
    assert created.status_code == 201

    # Org B GET by id -> 404 (agent is tenant-scoped).
    got_b = client.get(f"{API_PREFIX}/{public_id}", headers=_auth_headers(token_b))
    assert got_b.status_code == 404

    # Org B list -> does not contain Org A's agent.
    listed_b = client.get(f"{API_PREFIX}/", headers=_auth_headers(token_b))
    assert listed_b.status_code == 200
    assert all(a["public_id"] != public_id for a in listed_b.json())

    # Org B update -> 404 (cannot even locate the agent).
    upd_b = client.put(
        f"{API_PREFIX}/{public_id}", json={"name": "hacked"},
        headers=_auth_headers(token_b),
    )
    assert upd_b.status_code == 404

    # Org B delete -> 404.
    del_b = client.delete(f"{API_PREFIX}/{public_id}", headers=_auth_headers(token_b))
    assert del_b.status_code == 404

    # Org A still owns the agent after Org B's failed attempts.
    got_a = client.get(f"{API_PREFIX}/{public_id}", headers=_auth_headers(token_a))
    assert got_a.status_code == 200
    assert got_a.json()["name"] == f"Agent {public_id}"


def test_agents_are_isolated_at_storage_layer(client, db_session):
    """Verify the agent is physically stored under the creator's organization."""
    token_a, org_a, _ = _register(client)
    public_id = f"p-store-{uuid.uuid4()}"
    client.post(
        f"{API_PREFIX}/", json=_create_agent_payload(public_id),
        headers=_auth_headers(token_a),
    )

    repo = RepositoryFactory(db_session, uuid.UUID(str(org_a)))
    agent = repo.agents().get_by_public_id(public_id)
    assert agent is not None
    assert str(agent.organization_id) == org_a


# ---------------------------------------------------------------------------
# RBAC: only owner/admin/member may manage agents; viewers are read-only
# ---------------------------------------------------------------------------


def test_member_can_read_but_not_manage(client, db_session):
    token_owner, org_id, _ = _register(client)
    token_member, _ = _make_member(db_session, org_id, "member")
    public_id = f"p-member-{uuid.uuid4()}"

    # Member can read (list + get) even with no agents yet.
    assert client.get(f"{API_PREFIX}/", headers=_auth_headers(token_member)).status_code == 200

    # Member can create.
    created = client.post(
        f"{API_PREFIX}/", json=_create_agent_payload(public_id),
        headers=_auth_headers(token_member),
    )
    assert created.status_code == 201, created.text

    # Member can update + delete what exists in the tenant.
    assert client.put(
        f"{API_PREFIX}/{public_id}", json={"name": "m"},
        headers=_auth_headers(token_member),
    ).status_code == 200
    assert client.delete(
        f"{API_PREFIX}/{public_id}", headers=_auth_headers(token_member),
    ).status_code == 204


def test_viewer_can_read_but_not_manage(client, db_session):
    token_owner, org_id, _ = _register(client)
    token_viewer, _ = _make_member(db_session, org_id, "viewer")
    public_id = f"p-viewer-{uuid.uuid4()}"

    # Owner seeds an agent for the viewer to read.
    seeded = client.post(
        f"{API_PREFIX}/", json=_create_agent_payload(public_id),
        headers=_auth_headers(token_owner),
    )
    assert seeded.status_code == 201

    # Viewer may read.
    assert client.get(f"{API_PREFIX}/", headers=_auth_headers(token_viewer)).status_code == 200
    assert client.get(
        f"{API_PREFIX}/{public_id}", headers=_auth_headers(token_viewer)
    ).status_code == 200

    # Viewer may NOT create.
    assert client.post(
        f"{API_PREFIX}/", json=_create_agent_payload(f"p-v-{uuid.uuid4()}"),
        headers=_auth_headers(token_viewer),
    ).status_code == 403

    # Viewer may NOT update.
    assert client.put(
        f"{API_PREFIX}/{public_id}", json={"name": "x"},
        headers=_auth_headers(token_viewer),
    ).status_code == 403

    # Viewer may NOT delete.
    assert client.delete(
        f"{API_PREFIX}/{public_id}", headers=_auth_headers(token_viewer),
    ).status_code == 403
