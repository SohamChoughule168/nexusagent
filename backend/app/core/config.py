from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class ConfigurationError(Exception):
    """Raised when required configuration is missing or insecure."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: List[str] = [
        "pdf", "doc", "docx", "txt", "csv", "html", "md", "json"
    ]

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
