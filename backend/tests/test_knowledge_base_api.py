"""Knowledge Base API tests (Milestone 3).

The Knowledge Base API is the next functional component after the Conversation
Layer. It reuses the same tenant-isolation boundary: ``organization_id`` is
derived from the authenticated principal via ``app.core.auth_dependencies``,
never from request data.

Style mirrors ``test_conversation_api.py``: register a real user (yields a JWT
+ organization), then exercise the knowledge-base endpoints with a ``Bearer``
token. Each test registers a fresh organization so the UNIQUE
(organization_id, name) constraint never collides across tests.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.all_models import KnowledgeBase

API_PREFIX = "/api/v1/knowledge-bases"
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
    email = f"kb-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "KB Owner",
            "organization_name": f"KB Org {uuid.uuid4()}",
            "organization_slug": f"kb-org-{uuid.uuid4()}",
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

    # Cleanup: knowledge bases created via the API for this org.
    db_session.query(KnowledgeBase).filter(
        KnowledgeBase.organization_id == org_id
    ).delete(synchronize_session=False)
    db_session.commit()


# ---------------------------------------------------------------------------
# POST /knowledge-bases
# ---------------------------------------------------------------------------


def test_create_kb_requires_authentication(client):
    payload = {"name": "Product Docs"}
    response = client.post(f"{API_PREFIX}/", json=payload)
    assert response.status_code == 401


def test_create_kb_returns_201(client, auth_org):
    token, org_id = auth_org
    payload = {
        "name": "Product Docs",
        "description": "Documentation for the product",
        "chunk_strategy": "recursive",
    }
    response = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == 201

    body = response.json()
    assert body["name"] == "Product Docs"
    assert body["organization_id"] == org_id
    assert body["description"] == "Documentation for the product"
    # Model defaults are applied server-side.
    assert body["embedding_model"] == "text-embedding-3-small"
    assert body["chunk_size"] == 1000
    assert body["chunk_overlap"] == 200
    assert body["chunk_strategy"] == "recursive"
    assert "id" in body
    assert "created_at" in body


def test_create_kb_applies_custom_config(client, auth_org):
    token, org_id = auth_org
    payload = {
        "name": "Custom KB",
        "embedding_model": "text-embedding-3-large",
        "chunk_size": 500,
        "chunk_overlap": 50,
        "chunk_strategy": "fixed",
        "retrieval_config": {"top_k": 5},
    }
    response = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["embedding_model"] == "text-embedding-3-large"
    assert body["chunk_size"] == 500
    assert body["chunk_overlap"] == 50
    assert body["chunk_strategy"] == "fixed"
    assert body["retrieval_config"] == {"top_k": 5}


def test_create_kb_duplicate_name_conflicts(client, auth_org):
    token, org_id = auth_org
    payload = {"name": "Duplicate Name"}
    first = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert first.status_code == 201
    second = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert second.status_code == 409


def test_create_kb_missing_name_422(client, auth_org):
    token, org_id = auth_org
    response = client.post(
        f"{API_PREFIX}/", json={}, headers=_auth_headers(token)
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /knowledge-bases
# ---------------------------------------------------------------------------


def test_list_kbs_includes_default(client, auth_org):
    # Registration seeds a "Default Knowledge Base" per organization, so the
    # list is never empty for a freshly registered tenant.
    token, org_id = auth_org
    response = client.get(f"{API_PREFIX}/", headers=_auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    names = {kb["name"] for kb in body}
    assert "Default Knowledge Base" in names


def test_list_kbs_returns_created(client, auth_org):
    token, org_id = auth_org
    created = client.post(
        f"{API_PREFIX}/",
        json={"name": f"Listed KB {uuid.uuid4()}"},
        headers=_auth_headers(token),
    )
    assert created.status_code == 201
    created_id = created.json()["id"]

    response = client.get(f"{API_PREFIX}/", headers=_auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    ids = {kb["id"] for kb in body}
    assert created_id in ids


# ---------------------------------------------------------------------------
# GET /knowledge-bases/{id}
# ---------------------------------------------------------------------------


def _create_kb(client, token, name):
    response = client.post(
        f"{API_PREFIX}/", json={"name": name}, headers=_auth_headers(token)
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_get_kb_returns_200(client, auth_org):
    token, org_id = auth_org
    kb_id = _create_kb(client, token, f"Get KB {uuid.uuid4()}")
    response = client.get(
        f"{API_PREFIX}/{kb_id}", headers=_auth_headers(token)
    )
    assert response.status_code == 200
    assert response.json()["id"] == kb_id


def test_get_kb_invalid_id_400(client, auth_org):
    token, org_id = auth_org
    response = client.get(
        f"{API_PREFIX}/not-a-uuid", headers=_auth_headers(token)
    )
    assert response.status_code == 400


def test_get_kb_unknown_404(client, auth_org):
    token, org_id = auth_org
    response = client.get(
        f"{API_PREFIX}/{uuid.uuid4()}", headers=_auth_headers(token)
    )
    assert response.status_code == 404


def test_get_kb_requires_authentication(client, auth_org):
    token, org_id = auth_org
    kb_id = _create_kb(client, token, f"Auth KB {uuid.uuid4()}")
    response = client.get(f"{API_PREFIX}/{kb_id}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# PUT /knowledge-bases/{id}
# ---------------------------------------------------------------------------


def test_update_kb_returns_200(client, auth_org):
    token, org_id = auth_org
    kb_id = _create_kb(client, token, f"Update KB {uuid.uuid4()}")
    response = client.put(
        f"{API_PREFIX}/{kb_id}",
        json={"description": "Updated description", "chunk_size": 800},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "Updated description"
    assert body["chunk_size"] == 800
    # Untouched fields retain their values.
    assert body["chunk_overlap"] == 200


def test_update_kb_duplicate_name_conflicts(client, auth_org):
    token, org_id = auth_org
    _create_kb(client, token, "KB One")
    kb_two = _create_kb(client, token, "KB Two")
    response = client.put(
        f"{API_PREFIX}/{kb_two}",
        json={"name": "KB One"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 409


def test_update_kb_unknown_404(client, auth_org):
    token, org_id = auth_org
    response = client.put(
        f"{API_PREFIX}/{uuid.uuid4()}",
        json={"description": "x"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /knowledge-bases/{id}
# ---------------------------------------------------------------------------


def test_delete_kb_returns_204(client, auth_org):
    token, org_id = auth_org
    kb_id = _create_kb(client, token, f"Delete KB {uuid.uuid4()}")
    response = client.delete(
        f"{API_PREFIX}/{kb_id}", headers=_auth_headers(token)
    )
    assert response.status_code == 204

    follow_up = client.get(
        f"{API_PREFIX}/{kb_id}", headers=_auth_headers(token)
    )
    assert follow_up.status_code == 404


def test_delete_kb_unknown_404(client, auth_org):
    token, org_id = auth_org
    response = client.delete(
        f"{API_PREFIX}/{uuid.uuid4()}", headers=_auth_headers(token)
    )
    assert response.status_code == 404
