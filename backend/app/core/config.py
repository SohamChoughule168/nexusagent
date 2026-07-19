import json
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import DotEnvSettingsSource, EnvSettingsSource

# List[str] fields that accept a practical comma-separated value (in addition to
# a JSON list). pydantic-settings JSON-decodes every complex (non-scalar) field
# *before* any pydantic validator runs, so a value like
# ``BACKEND_CORS_ORIGINS=http://a,http://b`` would otherwise fail to load. The
# sources below leave these fields as raw strings so their ``field_validator``
# can parse both the comma-separated and JSON-list forms. This matters in BOTH
# the .env file (dotenv source) AND real environment variables (env source) —
# the containerised deployment has no .env inside the image and passes every
# value through the environment source (see docker-compose*.yml), so patching
# only the dotenv source would crash the app on startup.
_COMMA_LIST_FIELDS = frozenset(
    {"BACKEND_CORS_ORIGINS", "ALLOWED_EXTENSIONS", "ALLOWED_MIME_TYPES"}
)


class _CorsFriendlyDotEnvSource(DotEnvSettingsSource):
    """Dotenv source that leaves comma-list fields raw for their validators."""

    def prepare_field_value(self, field_name, field, value, value_is_complex):
        if field_name in _COMMA_LIST_FIELDS and isinstance(value, str):
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class _CorsFriendlyEnvSource(EnvSettingsSource):
    """OS-environment source that leaves comma-list fields raw for validators.

    Required for the containerised deployment: images carry no .env, so every
    setting arrives via real environment variables (docker-compose ``environment:``).
    """

    def prepare_field_value(self, field_name, field, value, value_is_complex):
        if field_name in _COMMA_LIST_FIELDS and isinstance(value, str):
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)
from typing import List, Optional


class ConfigurationError(Exception):
    """Raised when required configuration is missing or insecure."""


# Anchor env loading to the repository root so the .env is found regardless of
# the current working directory the application/worker is launched from.
# config.py lives at <root>/backend/app/core/config.py -> four parents up.
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        # Redact secret-like fields from repr/logs automatically.
        validate_assignment=True,
    )

    # Application
    APP_NAME: str = "NexusAgent AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Build metadata (Phase 4). Injected at image build time via Docker build
    # args (BUILD_GIT_SHA / BUILD_TIMESTAMP); surfaced by the /version endpoint.
    # Falls back to "unknown" when the image was built without them (local dev).
    BUILD_GIT_SHA: Optional[str] = None
    BUILD_TIMESTAMP: Optional[str] = None

    # ---- Observability (Milestone 7, Phase 5) ----
    # Namespace prefixed to every Prometheus metric (e.g. nexusagent_http_*).
    PROMETHEUS_NAMESPACE: str = "nexusagent"
    # Master switch for the /metrics endpoint + HTTP metrics middleware.
    METRICS_ENABLED: bool = True
    # Optional rotating file sinks. When unset, logs go to stdout/stderr
    # (the container-friendly default). When set, the corresponding logger
    # also writes to a size-capped, rotated file (see app/core/logging.py).
    LOG_FILE: Optional[str] = None
    ACCESS_LOG_FILE: Optional[str] = None
    # RotatingFileHandler tuning (bytes per file, retained copies).
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MiB
    LOG_BACKUP_COUNT: int = 5
    # Emit structured per-request access logs (method/path/status/latency).
    LOG_ACCESS_ENABLED: bool = True
    # Readiness gating. DB + storage are always required; Redis/LLM are
    # reported but do not force a 503 by default because the app degrades
    # gracefully without them. Flip these to make them hard dependencies.
    HEALTH_REQUIRE_REDIS: bool = False

    # Database. The synchronous psycopg2 driver is used at runtime (the app
    # strips any "+asyncpg" prefix defensively). asyncpg is intentionally NOT a
    # dependency, so keep this on the psycopg2 dialect.
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/nexusagent"

    # Connection-pool sizing (production tuning, Phase 4). Only applies when
    # DEBUG is False (in DEBUG we use NullPool so each request gets a fresh
    # connection — convenient for dev reload, not for throughput). These bound
    # the SQLAlchemy QueuePool: ``DB_POOL_SIZE`` steady connections + up to
    # ``DB_MAX_OVERFLOW`` extra under bursts, per backend worker process.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # Trusted reverse proxy. When true, FastAPI honours ``X-Forwarded-*`` set by
    # nginx so ``request.client`` reflects the real client and ``url_for`` /
    # redirects build the public scheme/host. ONLY enable when the backend is
    # NOT directly reachable from the internet (the nginx/edge is the sole
    # public entrypoint) — otherwise a client could spoof its IP. The production
    # compose (docker-compose.aws.yml) enables this because its backend publishes
    # no host port; the local single-host compose leaves it off because it
    # publishes :8000 for convenience.
    TRUST_PROXY: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_REFRESH_SECRET_KEY: str = "change-me-in-production"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LLM Providers (secrets - never log values)
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # Embeddings: "local" (deterministic, offline, default) or an
    # OpenAI-compatible provider ("openai"/"openrouter"). The API provider is
    # only used when this is set AND a corresponding API key is configured;
    # otherwise the local embedder is used so the pipeline runs without keys.
    EMBEDDINGS_PROVIDER: str = "local"

    # RAG answer generation: "local" (offline composer that returns the most
    # relevant retrieved context, default) or "openrouter"/"openai" to call a
    # real LLM for grounded answers. The LLM is only used when this is set AND
    # a key is configured; otherwise the local composer keeps it testable.
    RAG_LLM_PROVIDER: str = "local"
    RAG_LLM_MODEL: str = "openai/gpt-4o-mini"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string or a JSON list for CORS origins.

        pydantic-settings only understands JSON for complex types, so a
        practical ``http://a,http://b`` value from ``.env`` would otherwise
        fail to validate. This keeps validation in place (we never bypass it)
        while accepting both formats safely.
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                # Accepts a JSON-encoded list, e.g. '["http://a","http://b"]'.
                return [str(item).strip() for item in json.loads(stripped)]
            # Practical comma-separated value, e.g. 'http://a,http://b'.
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Use the comma-list-friendly env + dotenv sources.

        Both the OS-environment and dotenv sources are replaced so
        comma-separated list values parse correctly whether the app is
        configured via a .env file (local) or real environment variables
        (containers — the image carries no .env).
        """
        return (
            init_settings,
            _CorsFriendlyEnvSource(settings_cls),
            _CorsFriendlyDotEnvSource(settings_cls),
            file_secret_settings,
        )

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: List[str] = [
        "pdf", "doc", "docx", "txt", "csv", "html", "md", "json"
    ]
    # MIME types accepted by the Document Upload API this milestone. PDF only
    # for now ("PDF initially"); widen as later milestones add parsers.
    ALLOWED_MIME_TYPES: List[str] = ["application/pdf"]

    @field_validator("ALLOWED_EXTENSIONS", "ALLOWED_MIME_TYPES", mode="before")
    @classmethod
    def _parse_str_list(cls, value: object) -> object:
        """Accept a comma-separated string or a JSON list for these fields.

        Mirrors the CORS parser so operators can set a plain
        ``ALLOWED_EXTENSIONS=pdf,txt`` in .env / the environment without hitting
        pydantic-settings' JSON-only decoding of complex fields.
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return [str(item).strip() for item in json.loads(stripped)]
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    # Local directory where uploaded raw bytes are persisted (metadata only;
    # no parsing/extraction this milestone). Created on demand.
    UPLOAD_STORAGE_DIR: str = str(ROOT_DIR / "storage" / "uploads")

    # Cost Tracking
    ENABLE_COST_TRACKING: bool = True

    # Security
    SECURITY_PASSWORD_SALT: str = "change-me-in-production"
    SECURITY_FORCE_DEV_MODE: bool = False

    # Feature Flags
    ENABLE_WEBHOOK_TOOL: bool = True
    ENABLE_LEAD_CAPTURE_TOOL: bool = True
    ENABLE_HUMAN_ESCALATION_TOOL: bool = True

    # Tool Execution Engine (Milestone 4, Phase 2) -- safety / resource bounds
    # applied by the engine to every tool run. These are coarse, engine-level
    # guards; the dedicated Safe-Execution hardening layer is a later component.
    TOOL_EXECUTION_TIMEOUT_SECONDS: float = 15.0
    TOOL_EXECUTION_MAX_OUTPUT_CHARS: int = 10000

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    def validate(self) -> None:
        """Validate required configuration and fail fast in production.

        Production (``DEBUG is False``) refuses to start when a required secret
        or connection string is missing or still set to an insecure development
        default, or when a remote LLM/embeddings provider is selected without
        its API key. Development (``DEBUG is True``) only logs warnings so local
        workflows can keep using defaults. Secret values are never logged.
        """
        # Values that must never survive into a production deployment.
        insecure = {"", "change-me", "change-me-in-production", "changeme", "change_me"}

        errors: list[str] = []

        # Crypto secrets: JWT signing + password-hashing salt.
        for name in ("JWT_SECRET_KEY", "JWT_REFRESH_SECRET_KEY", "SECURITY_PASSWORD_SALT"):
            value = getattr(self, name)
            if not value or value in insecure:
                errors.append(f"{name} is missing or uses an insecure default")

        # Required connection strings (managed services in production).
        if not self.DATABASE_URL:
            errors.append("DATABASE_URL is missing")
        if not self.REDIS_URL:
            errors.append("REDIS_URL is missing")

        # Remote LLM / embeddings providers require their API key. The "local"
        # providers have offline fallbacks, so they are exempt — this honours
        # the documented offline mode while still refusing to boot an
        # openrouter/openai configuration with no key.
        provider_keys = {
            "openrouter": self.OPENROUTER_API_KEY,
            "openai": self.OPENAI_API_KEY,
        }
        for setting, provider in (
            ("EMBEDDINGS_PROVIDER", self.EMBEDDINGS_PROVIDER),
            ("RAG_LLM_PROVIDER", self.RAG_LLM_PROVIDER),
        ):
            if provider in provider_keys and not provider_keys[provider]:
                errors.append(f"{setting}={provider} is set but its API key is missing")

        if not errors:
            return

        if self.DEBUG:
            # Development: surface misconfiguration but keep booting.
            from app.core.logging import get_logger

            for err in errors:
                get_logger(__name__).warning(
                    "config_insecure_default",
                    detail=err,
                    msg="Insecure/incomplete configuration (development mode: not fatal)",
                )
            return

        raise ConfigurationError(
            "Refusing to start with invalid production configuration: "
            + "; ".join(errors)
        )


settings = Settings()
