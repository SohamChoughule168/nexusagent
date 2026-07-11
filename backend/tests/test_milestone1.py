import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_app_object_is_constructable():
    """Application startup / import must succeed."""
    assert app is not None
    assert app.title == "NexusAgent AI"


def test_health_returns_200(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_schema(client: TestClient):
    response = client.get("/health")
    assert response.json() == {"status": "healthy"}


def test_unknown_route_returns_404(client: TestClient):
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404


def test_request_id_header_present(client: TestClient):
    response = client.get("/health")
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"]


def test_security_headers_present(client: TestClient):
    response = client.get("/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"


def test_api_v1_router_mounted(client: TestClient):
    # Verify the auth and agents sub-routers are mounted under /api/v1
    # without depending on a database connection.
    mounted_paths = [getattr(route, "path", "") for route in app.routes]
    assert any("/api/v1/agents" in p for p in mounted_paths)
    assert any("/api/v1/auth" in p for p in mounted_paths)
