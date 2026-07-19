"""Tests for the session-required password-change endpoint (K1).

The endpoint must reject unauthenticated callers and only change the password
of the user identified by the Bearer session — never a user supplied in the
request body (the pre-GA no-session design widened account-takeover surface).
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

AUTH_PREFIX = "/api/v1/auth"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _register(client: TestClient):
    email = f"user-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "OldPass#123",
            "full_name": "Owner",
            "organization_name": f"Org {uuid.uuid4()}",
            "organization_slug": f"org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], email


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_change_password_requires_auth(client):
    resp = client.post(
        f"{AUTH_PREFIX}/change-password",
        json={"current_password": "OldPass#123", "new_password": "NewPass#456"},
    )
    assert resp.status_code == 401


def test_change_password_succeeds_with_session(client):
    token, email = _register(client)

    resp = client.post(
        f"{AUTH_PREFIX}/change-password",
        headers=_headers(token),
        json={"current_password": "OldPass#123", "new_password": "NewPass#456"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"]

    # The new password must authenticate; the old one must not.
    login_new = client.post(
        f"{AUTH_PREFIX}/login",
        data={"username": email, "password": "NewPass#456"},
    )
    assert login_new.status_code == 200

    login_old = client.post(
        f"{AUTH_PREFIX}/login",
        data={"username": email, "password": "OldPass#123"},
    )
    assert login_old.status_code == 401


def test_change_password_rejects_wrong_current_password(client):
    token, _ = _register(client)

    resp = client.post(
        f"{AUTH_PREFIX}/change-password",
        headers=_headers(token),
        json={"current_password": "WrongPass#000", "new_password": "NewPass#456"},
    )
    assert resp.status_code == 400
    assert "incorrect" in resp.json()["detail"].lower()


def test_change_password_rejects_email_in_body(client):
    """The endpoint derives the user from the session; an email in the body is
    rejected by the (now email-free) schema."""
    token, _ = _register(client)

    resp = client.post(
        f"{AUTH_PREFIX}/change-password",
        headers=_headers(token),
        json={
            "email": "someone-else@example.com",
            "current_password": "OldPass#123",
            "new_password": "NewPass#456",
        },
    )
    assert resp.status_code == 422
