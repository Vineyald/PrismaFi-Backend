from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables and an optional `.env` file."""

    # hide_input_in_errors: a malformed URL must not echo its credentials into startup logs.
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore", hide_input_in_errors=True
    )

    # Fails closed: a deploy that forgets ENVIRONMENT gets production behavior (no docs).
    environment: Literal["development", "production"] = "production"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Required: the app refuses to start without them.
    database_url: PostgresDsn
    redis_url: RedisDsn
    # Signs access tokens (HS256). Generate with:
    # python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret: SecretStr = Field(min_length=32)

    # Browser origins allowed to call the API cross-origin. Empty disables CORS,
    # which is the default because the frontend reaches the API same-origin (dev proxy).
    cors_origins: list[str] = []


settings = Settings()
