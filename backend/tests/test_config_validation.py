"""Production startup validation (fail-fast) tests.

These exercise ``Settings.validate()`` directly so the policy is covered without
booting the ASGI app. ``validate()`` raises ``ConfigurationError`` in production
(``DEBUG is False``) and only warns in development (``DEBUG is True``).
"""
import pytest

from app.core.config import ConfigurationError, Settings


def _base(**overrides) -> Settings:
    """A valid production-looking config; override fields to induce failures."""
    params = dict(
        DEBUG=False,
        JWT_SECRET_KEY="production-secret-value",
        JWT_REFRESH_SECRET_KEY="production-refresh-value",
        SECURITY_PASSWORD_SALT="production-salt-value",
        DATABASE_URL="postgresql+psycopg2://u:p@db:5432/app",
        REDIS_URL="redis://redis:6379/0",
        EMBEDDINGS_PROVIDER="local",
        RAG_LLM_PROVIDER="local",
    )
    params.update(overrides)
    return Settings(**params)


def test_valid_production_config_passes():
    _base().validate()  # must not raise


def test_insecure_jwt_secret_fails_in_production():
    with pytest.raises(ConfigurationError):
        _base(JWT_SECRET_KEY="change-me-in-production").validate()


def test_insecure_refresh_secret_fails_in_production():
    with pytest.raises(ConfigurationError):
        _base(JWT_REFRESH_SECRET_KEY="change-me").validate()


def test_insecure_password_salt_fails_in_production():
    with pytest.raises(ConfigurationError):
        _base(SECURITY_PASSWORD_SALT="change-me-in-production").validate()


def test_missing_database_url_fails_in_production():
    with pytest.raises(ConfigurationError):
        _base(DATABASE_URL="").validate()


def test_missing_redis_url_fails_in_production():
    with pytest.raises(ConfigurationError):
        _base(REDIS_URL="").validate()


def test_openrouter_provider_without_key_fails():
    with pytest.raises(ConfigurationError):
        _base(RAG_LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="").validate()


def test_openai_provider_without_key_fails():
    with pytest.raises(ConfigurationError):
        _base(EMBEDDINGS_PROVIDER="openai", OPENAI_API_KEY="").validate()


def test_openrouter_provider_with_key_passes():
    _base(RAG_LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-test").validate()


def test_dev_mode_allows_insecure_defaults():
    # DEBUG=True must never raise, even with insecure secrets / missing URLs.
    settings = _base(
        DEBUG=True,
        JWT_SECRET_KEY="change-me-in-production",
        DATABASE_URL="",
    )
    settings.validate()  # must not raise
