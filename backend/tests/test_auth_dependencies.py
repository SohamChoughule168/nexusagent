"""Tests for the API-layer authentication & authorization dependencies.

Covers the protected conversation surface (the integration point for
``app.core.auth_dependencies``) plus direct unit tests of the RBAC
``require_roles`` factory. These guard tenant isolation at the API boundary:
a valid token from organization A must never be able to read organization B's
data, and missing/invalid tokens must be rejected with 401.
"""
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_current_user, require_roles
from app.core.database import get_sessionmaker as SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.all_models import Agent
from app.models.organization import Organization
from app.models.user import User
from app.services.tenant_context import TenantContext

API_PREFIX = "/api/v1/conversations"
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


def _make_agent(db: Session, org_id: str) -> str:
    agent = Agent(
        organization_id=org_id,
        data={
            "name": "Test Agent",
            "system_prompt": "sys",
            "public_id": f"test-agent-{uuid.uuid4()}",
        },
    )
    agent.id = uuid.uuid4()
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return str(agent.id)


# ---------------------------------------------------------------------------
# 401: missing / malformed tokens
# ---------------------------------------------------------------------------


def test_protected_endpoint_requires_token(client):
    payload = {"agent_id": str(uuid.uuid4()), "session_id": f"s-{uuid.uuid4()}"}
    response = client.post(f"{API_PREFIX}/", json=payload)
    assert response.status_code == 401


def test_protected_endpoint_rejects_malformed_token(client):
    payload = {"agent_id": str(uuid.uuid4()), "session_id": f"s-{uuid.uuid4()}"}
    response = client.post(
        f"{API_PREFIX}/", json=payload, headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 200: valid token resolves the correct tenant
# ---------------------------------------------------------------------------


def test_protected_endpoint_accepts_valid_token(client, db_session):
    token, org_id = _register(client)
    agent_id = _make_agent(db_session, org_id)

    payload = {"agent_id": agent_id, "session_id": f"s-{uuid.uuid4()}"}
    response = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == 201
    # organization_id on the created resource must equal the token's org,
    # proving the tenant was derived from the principal (not request data).
    assert response.json()["organization_id"] == org_id


# ---------------------------------------------------------------------------
# 403/404: tenant isolation enforced at the API boundary
# ---------------------------------------------------------------------------


def test_protected_endpoint_isolates_tenants(client, db_session):
    # Owner A creates a conversation in their org.
    token_a, org_a = _register(client)
    agent_a = _make_agent(db_session, org_a)
    conv_id = (
        client.post(
            f"{API_PREFIX}/",
            json={"agent_id": agent_a, "session_id": f"s-{uuid.uuid4()}"},
            headers=_auth_headers(token_a),
        )
        .json()["id"]
    )

    # Owner B (a different org, but a perfectly valid token) must not see it.
    token_b, _org_b = _register(client)
    response = client.get(
        f"{API_PREFIX}/{conv_id}/messages", headers=_auth_headers(token_b)
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# get_current_user: inactive user is rejected
# ---------------------------------------------------------------------------


def test_inactive_user_token_rejected(client, db_session):
    token, org_id = _register(client)
    # Look up the registered user and deactivate it.
    user = db_session.query(User).filter(User.email.like("owner-%")).order_by(User.created_at.desc()).first()
    assert user is not None
    user.is_active = False
    db_session.commit()

    payload = {"agent_id": str(uuid.uuid4()), "session_id": f"s-{uuid.uuid4()}"}
    response = client.post(
        f"{API_PREFIX}/", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == 401


def test_get_current_user_rejects_inactive_user_directly(db_session):
    org = Organization(id=str(uuid.uuid4()), name="O", slug=f"o-{uuid.uuid4()}")
    user = User(
        id=str(uuid.uuid4()),
        email=f"u-{uuid.uuid4()}@example.com",
        is_active=False,
        password_hash="x",
    )
    db_session.add_all([org, user])
    db_session.commit()

    token = create_access_token(user.id, org.id)
    # Decoding works, but the dependency must refuse an inactive principal.
    with pytest.raises(HTTPException) as exc:
        get_current_user(
            credentials=type("C", (), {"credentials": token})(),
            db=db_session,
        )
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# require_roles: RBAC factory
# ---------------------------------------------------------------------------


def _ctx(role: str) -> TenantContext:
    return TenantContext(
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role=role,
    )


def test_require_roles_permits_matching_role():
    enforce = require_roles("owner", "admin")
    ctx = _ctx("owner")
    assert enforce(current_tenant=ctx) is ctx


def test_require_roles_permits_any_when_no_roles_specified():
    enforce = require_roles()
    ctx = _ctx("viewer")
    assert enforce(current_tenant=ctx) is ctx


def test_require_roles_denies_insufficient_role():
    enforce = require_roles("owner", "admin")
    with pytest.raises(HTTPException) as exc:
        enforce(current_tenant=_ctx("viewer"))
    assert exc.value.status_code == 403


def test_require_roles_denies_member_for_admin_only():
    enforce = require_roles("owner", "admin")
    with pytest.raises(HTTPException) as exc:
        enforce(current_tenant=_ctx("member"))
    assert exc.value.status_code == 403
