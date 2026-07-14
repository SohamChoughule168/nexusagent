import json
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import DotEnvSettingsSource


class _CorsFriendlyDotEnvSource(DotEnvSettingsSource):
    """Dotenv source that does not JSON-decode the CORS origins field.

    pydantic-settings JSON-decodes every complex (non-scalar) field *before*
    any pydantic validator runs, which makes a practical comma-separated
    ``BACKEND_CORS_ORIGINS=http://a,http://b`` value fail to load. This source
    leaves that one field as its raw string so the CORS ``field_validator`` can
    parse comma-separated lists and JSON lists safely. All other fields keep
    their normal behaviour.
    """

    def prepare_field_value(self, field_name, field, value, value_is_complex):
        if field_name == "BACKEND_CORS_ORIGINS" and isinstance(value, str):
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
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/nexusagent"

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
        """Use the CORS-friendly dotenv source instead of the default one."""
        return (
            init_settings,
            env_settings,
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

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    def validate(self) -> None:
        """Validate required configuration without leaking secret values.

        Raises ConfigurationError if required values are empty. Logs a
        warning (does not raise) when insecure development defaults are used.
        """
        missing = []
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")
        if not self.JWT_SECRET_KEY:
            missing.append("JWT_SECRET_KEY")
        if not self.JWT_REFRESH_SECRET_KEY:
            missing.append("JWT_REFRESH_SECRET_KEY")
        if missing:
            raise ConfigurationError(
                "Missing required configuration: " + ", ".join(missing)
            )

        insecure_secrets = {
            "JWT_SECRET_KEY": self.JWT_SECRET_KEY,
            "JWT_REFRESH_SECRET_KEY": self.JWT_REFRESH_SECRET_KEY,
            "SECURITY_PASSWORD_SALT": self.SECURITY_PASSWORD_SALT,
        }
        for name, value in insecure_secrets.items():
            if value in ("change-me-in-production", "change-me", ""):
                # Imported lazily to avoid a logging import cycle at startup.
                from app.core.logging import get_logger

                get_logger(__name__).warning(
                    "insecure_default_secret",
                    setting=name,
                    msg="Using an insecure default secret; set a strong value in production",
                )


settings = Settings()
