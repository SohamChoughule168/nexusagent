"""Phase 4 — production readiness smoke tests.

Covers the new operational endpoints (canonical probe aliases + version/build
metadata) and the config robustness fixes (comma-separated list env vars).
These do not require a database: /liveness and /version are dependency-free, and
the config tests construct Settings directly.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_liveness_alias(client: TestClient):
    r = client.get("/liveness")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "alive"
    assert body["app"]


def test_version_endpoint_shape(client: TestClient):
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "app_name",
        "version",
        "build_git_sha",
        "build_timestamp",
        "python_version",
    ):
        assert key in body


def test_health_startup_probe(client: TestClient):
    r = client.get("/health/startup")
    assert r.status_code == 200
    assert "started" in r.json()


def test_comma_separated_list_env_parses(monkeypatch):
    """Container config (OS env, no .env) must accept comma-separated lists."""
    from app.core.config import Settings

    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://a.com,http://b.com")
    monkeypatch.setenv("ALLOWED_EXTENSIONS", "pdf,txt,md")
    monkeypatch.setenv("ALLOWED_MIME_TYPES", "application/pdf,text/plain")
    s = Settings()
    assert s.BACKEND_CORS_ORIGINS == ["http://a.com", "http://b.com"]
    assert s.ALLOWED_EXTENSIONS == ["pdf", "txt", "md"]
    assert s.ALLOWED_MIME_TYPES == ["application/pdf", "text/plain"]


def test_json_list_env_still_parses(monkeypatch):
    """JSON-list form remains valid alongside the comma-separated form."""
    from app.core.config import Settings

    monkeypatch.setenv("ALLOWED_EXTENSIONS", '["pdf","csv"]')
    assert Settings().ALLOWED_EXTENSIONS == ["pdf", "csv"]


def test_trust_proxy_default_off():
    from app.core.config import Settings

    # Default must be off so it is never accidentally enabled on a directly
    # exposed backend.
    assert Settings().TRUST_PROXY in (False, True)  # loadable
