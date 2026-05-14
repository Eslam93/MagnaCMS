"""Runtime configuration sourced from environment variables and `.env`.

All settings are validated at startup. Placeholder secrets are accepted in
local/dev environments to keep onboarding cheap, but rejected in
staging/production by a model validator — the service refuses to boot
rather than silently running with insecure defaults.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PROD = "production"


class AIProviderMode(StrEnum):
    OPENAI = "openai"
    BEDROCK = "bedrock"
    MOCK = "mock"


def _split_csv(value: str | list[str]) -> list[str]:
    """Accept either a CSV string or an already-parsed list."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CSVList = Annotated[list[str], BeforeValidator(_split_csv)]


_PLACEHOLDER_PREFIXES = ("REPLACE_ME", "sk-proj-REPLACE", "dev-only-")


def _is_placeholder(value: str) -> bool:
    return value == "" or any(value.startswith(p) for p in _PLACEHOLDER_PREFIXES)


class Settings(BaseSettings):
    """Application settings. Singleton, accessed via `get_settings()`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App metadata ---
    app_name: str = "MagnaCMS"
    app_version: str = "0.1.0"
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"

    # --- AI provider ---
    ai_provider_mode: AIProviderMode = AIProviderMode.OPENAI

    # --- OpenAI ---
    openai_api_key: SecretStr | None = None
    openai_text_model: str = "gpt-5.4-mini-2026-03-17"
    openai_image_model: str = "gpt-image-1"
    openai_image_quality: str = "medium"
    openai_timeout_seconds: int = 60
    openai_max_retries: int = 3

    # --- AWS ---
    aws_region: str = "us-east-1"

    # --- Database ---
    database_url: str = "postgresql+asyncpg://app:app@postgres:5432/app"

    # --- Redis ---
    use_redis: bool = True
    redis_url: str = "redis://redis:6379/0"

    # --- Auth ---
    jwt_secret: SecretStr = SecretStr("dev-only-REPLACE_ME_with_openssl_rand_hex_32")
    jwt_access_token_ttl_seconds: int = 900
    jwt_refresh_token_ttl_seconds: int = 2592000

    # --- Storage ---
    s3_bucket_images: str = "ai-content-images-dev"
    images_cdn_base_url: str = "http://localhost:8000/local-images"

    # --- CORS ---
    cors_origins: CSVList = Field(
        default_factory=lambda: ["http://localhost:3000"],
    )

    # --- Observability ---
    sentry_dsn: str = ""

    @model_validator(mode="after")
    def _reject_placeholders_in_protected_envs(self) -> Settings:
        """Fail fast if placeholder secrets reach a protected environment."""
        if self.environment in {Environment.PROD, Environment.STAGING}:
            if _is_placeholder(self.jwt_secret.get_secret_value()):
                raise ValueError(
                    f"JWT_SECRET must be set to a strong random value "
                    f"(environment={self.environment.value})"
                )
            if self.ai_provider_mode == AIProviderMode.OPENAI:
                key = self.openai_api_key
                if key is None or _is_placeholder(key.get_secret_value()):
                    raise ValueError(
                        f"OPENAI_API_KEY must be set when AI_PROVIDER_MODE=openai "
                        f"(environment={self.environment.value})"
                    )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Safe to use as a FastAPI dependency."""
    return Settings()
