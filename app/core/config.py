import logging
import os
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Old hardcoded default that must no longer be used as an implicit fallback.
_OLD_DEFAULT_ADMIN_PASSWORD = "AdminPassword123!"


class Settings(BaseSettings):
    # API Metadata
    PROJECT_NAME: str = "Cognitive ERP API"
    PROJECT_VERSION: str = "1.0.0"

    # Environment Settings
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = ""

    # Database Settings
    DATABASE_URL: str
    DB_ECHO: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security Settings
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Admin seed credentials
    # H10: No hardcoded default. Must be provided via env; if missing, startup
    # seeding raises a clear error. If someone still sets it to the old leaked
    # default we log a loud warning below.
    DEFAULT_ADMIN_PASSWORD: str = ""

    # Organization timezone (IANA name, e.g. "Asia/Kolkata")
    ORG_TIMEZONE: str = "Asia/Kolkata"

    # Frontend Settings
    FRONTEND_URL: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v in ("replace_with_secure_secret", "", "changeme") or len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters and cryptographically random. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        return v

    @field_validator('ALGORITHM')
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        allowed = {"HS256", "HS384", "HS512"}
        if v not in allowed:
            raise ValueError(f"ALGORITHM must be one of {allowed}")
        return v

    @field_validator("DEFAULT_ADMIN_PASSWORD")
    @classmethod
    def validate_admin_password(cls, v: str) -> str:
        # H10: warn loudly if the old leaked default is still in use.
        if v and v == _OLD_DEFAULT_ADMIN_PASSWORD:
            logger.warning(
                "[Security] DEFAULT_ADMIN_PASSWORD is set to the old hardcoded "
                "default value. Change it immediately in your .env."
            )
        return v


settings = Settings()

# Centralized super-admin role codes — single source of truth used across the app
SUPER_ADMIN_CODES: frozenset[str] = frozenset({
    "ADMIN", "CEO", "CHIEF_EXECUTIVE_OFFICER", "ADMINISTRATOR"
})
