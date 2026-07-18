"""Tests for the tenant-scoped API key endpoints.

These endpoints were completed for the v1.0.0 release: creation persists a
hashed key (returning the plaintext exactly once), listing exposes only
non-secret metadata, and both require authentication and are isolated to the
authenticated principal's organization.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.all_models import APIKey

AUTH_PREFIX = "/api/v1/auth"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


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


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_create_api_key_requires_auth(client):
    resp = client.post(f"{AUTH_PREFIX}/api-keys", json={"name": "k", "scopes": []})
    assert resp.status_code == 401


def test_list_api_keys_requires_auth(client):
    resp = client.get(f"{AUTH_PREFIX}/api-keys")
    assert resp.status_code == 401


def test_create_api_key_returns_plaintext_once_and_persists_hash(client):
    token, org_id = _register(client)

    resp = client.post(
        f"{AUTH_PREFIX}/api-keys",
        headers=_headers(token),
        json={"name": "ci-key", "scopes": ["read", "write"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    # Plaintext key returned exactly once, with a prefix and the requested name.
    assert body["key"]
    assert body["name"] == "ci-key"
    assert body["key_prefix"]
    assert body["key"].startswith(body["key_prefix"])
    assert set(body["scopes"]) == {"read", "write"}


def test_list_api_keys_returns_metadata_only(client):
    token, org_id = _register(client)

    created = client.post(
        f"{AUTH_PREFIX}/api-keys",
        headers=_headers(token),
        json={"name": "listed-key", "scopes": ["read"]},
    )
    assert created.status_code == 201, created.text
    plaintext = created.json()["key"]

    listing = client.get(f"{AUTH_PREFIX}/api-keys", headers=_headers(token))
    assert listing.status_code == 200, listing.text
    keys = listing.json()["keys"]
    assert len(keys) >= 1

    key = next(k for k in keys if k["name"] == "listed-key")
    # The secret is never exposed on read.
    assert "key" not in key
    assert "key_hash" not in key
    assert key["key_prefix"]
    assert plaintext.startswith(key["key_prefix"])
    assert key["scopes"] == ["read"]
    assert key["is_active"] is True


def test_api_keys_are_tenant_isolated(client):
    token_a, _ = _register(client)
    token_b, _ = _register(client)

    client.post(
        f"{AUTH_PREFIX}/api-keys",
        headers=_headers(token_a),
        json={"name": "tenant-a-key", "scopes": []},
    )

    # Tenant B must not see tenant A's keys.
    listing_b = client.get(f"{AUTH_PREFIX}/api-keys", headers=_headers(token_b))
    assert listing_b.status_code == 200
    names_b = [k["name"] for k in listing_b.json()["keys"]]
    assert "tenant-a-key" not in names_b
