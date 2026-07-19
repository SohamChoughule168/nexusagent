"""Tests for registration edge cases (K6).

A non-unique ``organization_slug`` must surface as a friendly 409, not a 500
from an uncaught IntegrityError.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

AUTH_PREFIX = "/api/v1/auth"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _register(client: TestClient, slug: str):
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": f"user-{uuid.uuid4()}@example.com",
            "password": "TestPass#123",
            "full_name": "Owner",
            "organization_name": f"Org {uuid.uuid4()}",
            "organization_slug": slug,
        },
    )
    return resp


def test_duplicate_slug_returns_409(client):
    slug = f"dup-{uuid.uuid4()}"
    first = _register(client, slug)
    assert first.status_code == 201, first.text

    second = _register(client, slug)
    assert second.status_code == 409, second.text
    assert "slug" in second.json()["detail"].lower()
