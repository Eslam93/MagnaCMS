"""Runtime configuration sourced from environment variables and `.env`.

All settings are validated at startup. Placeholder secrets are accepted in
local/dev environments to keep onboarding cheap, but rejected in
staging/production by a model validator — the service refuses to boot
rather than silently running with insecure defaults.
"""

from __future__ import annotations

import base64
import binascii
import math
import re
from collections import Counter
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

# Minimum decoded JWT secret length in bytes — 32 bytes (256 bits) matches
# `openssl rand -hex 32` and the HS256 key-size recommendation.
_JWT_SECRET_MIN_BYTES = 32

# Strict format gate. We accept ONLY:
#   - hex strings of >=64 chars (decode to >=32 bytes)
#   - base64 / base64url strings that decode to >=32 bytes AND whose
#     decoded bytes have enough Shannon entropy to look like real
#     random material (English text base64-decodes to low-entropy bytes
#     and slipped past the previous "format + length" check)
# Anything else — including 32+ char passphrases — is rejected.
_HEX_RE = re.compile(r"\A[0-9a-fA-F]+\Z")
_BASE64_RE = re.compile(r"\A[A-Za-z0-9+/=_-]+\Z")

# Shannon-entropy floor for decoded JWT-secret bytes.
#
# The empirical entropy of a 32-byte sample is bounded by log2(32) = 5.0
# bits/byte — the maximum is only reached when every byte is unique.
# Random 32 bytes uniformly drawn from 256 values typically have ~30
# unique bytes (birthday paradox), so real `openssl rand -base64 32`
# output sits around 4.85-4.95 bits/byte. A threshold of 5.0 was
# rejecting half of legitimate random secrets.
#
# We pick 4.5 — comfortably above English text (~4.0-4.5) and the
# obvious repeating-pattern failures, comfortably below the empirical
# floor of true random 32-byte material. The hex path applies the same
# check so `"0"*64` and `"01"*32` (which were previously accepted) now
# fail.
_JWT_SECRET_MIN_ENTROPY_BITS = 4.5


def _shannon_entropy_bits_per_byte(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    total = len(data)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def _is_placeholder(value: str) -> bool:
    return value == "" or any(value.startswith(p) for p in _PLACEHOLDER_PREFIXES)


def _decoded_bytes_if_base64(value: str) -> bytes | None:
    """Return decoded bytes if `value` is valid standard- or url-safe base64.

    Tries url-safe first (matches `secrets.token_urlsafe`), then standard.
    Padding is fixed up to be lenient against `secrets.token_urlsafe` output
    which omits trailing `=`.
    """
    padded = value + "=" * (-len(value) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return decoder(padded)
        except (ValueError, binascii.Error):
            continue
    return None


def _is_weak_jwt_secret(value: str) -> str | None:
    """Return a human-readable reason if `value` is too weak for JWT signing,
    or None if it passes."""
    if _is_placeholder(value):
        return "value is a placeholder"

    # Hex path: 2 hex chars per byte, so 32 bytes = 64 chars minimum.
    # Apply the same entropy check the base64 path uses — otherwise
    # `"0" * 64` and `"01" * 32` would slip through format+length alone.
    if _HEX_RE.fullmatch(value) and len(value) >= _JWT_SECRET_MIN_BYTES * 2:
        decoded_hex = bytes.fromhex(value)
        if _shannon_entropy_bits_per_byte(decoded_hex) >= _JWT_SECRET_MIN_ENTROPY_BITS:
            return None
        return (
            "value is the right hex length but decodes to a low-entropy payload "
            "(repeated bytes or trivial pattern). Use `openssl rand -hex 32` "
            "for real random material."
        )

    # Base64 / base64url path — also requires the decoded bytes to look
    # like crypto material rather than English text that happens to be
    # valid base64.
    if _BASE64_RE.fullmatch(value):
        decoded = _decoded_bytes_if_base64(value)
        if decoded is not None and len(decoded) >= _JWT_SECRET_MIN_BYTES:
            if _shannon_entropy_bits_per_byte(decoded) >= _JWT_SECRET_MIN_ENTROPY_BITS:
                return None
            return (
                "value base64-decodes to enough bytes but the decoded payload "
                "has low Shannon entropy — looks like text, not cryptographic "
                "material. Use `openssl rand -base64 32` or `python -c 'import "
                "secrets; print(secrets.token_urlsafe(32))'`."
            )

    return (
        "value is not a recognized strong secret format. "
        "Provide one of: (a) >=64 hex chars from `openssl rand -hex 32`, or "
        "(b) base64/base64url string decoding to >=32 bytes from "
        "`openssl rand -base64 32` / `python -c 'import secrets; "
        "print(secrets.token_urlsafe(32))'`."
    )


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
    # Escape hatch: allow AI_PROVIDER_MODE=mock outside `local`. Off by
    # default so a misconfigured production deploy fails at startup
    # rather than silently serving canned content to real users.
    allow_mock_provider: bool = False

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
    def _reject_weak_secrets_outside_local(self) -> Settings:
        """Fail fast if secrets are weak in any non-local environment.

        `local` is the developer's docker-compose stack — placeholder values
        are tolerated so onboarding stays cheap. Everything else (dev shared
        cloud, staging, production) is treated as protected.
        """
        if self.environment == Environment.LOCAL:
            return self

        reason = _is_weak_jwt_secret(self.jwt_secret.get_secret_value())
        if reason is not None:
            raise ValueError(
                f"JWT_SECRET is unacceptable in environment={self.environment.value}: {reason}"
            )

        if self.ai_provider_mode == AIProviderMode.OPENAI:
            key = self.openai_api_key
            if key is None or _is_placeholder(key.get_secret_value()):
                raise ValueError(
                    f"OPENAI_API_KEY must be set when AI_PROVIDER_MODE=openai "
                    f"(environment={self.environment.value})"
                )

        # Eager provider-mode guards. The provider factory is lazy (builds
        # on first call), so a misconfigured deploy would otherwise be
        # healthy at startup and explode at first request. Move both
        # "this mode can't actually work" checks here.
        if self.ai_provider_mode == AIProviderMode.MOCK and not self.allow_mock_provider:
            raise ValueError(
                f"AI_PROVIDER_MODE=mock is not allowed in environment="
                f"{self.environment.value}. Set ALLOW_MOCK_PROVIDER=true "
                "to override (intended only for demo/staging environments, "
                "never for real-user-facing traffic)."
            )
        if self.ai_provider_mode == AIProviderMode.BEDROCK:
            raise ValueError(
                "AI_PROVIDER_MODE=bedrock is documented but not implemented. "
                "Either switch to AI_PROVIDER_MODE=openai (recommended) or "
                "AI_PROVIDER_MODE=mock + ALLOW_MOCK_PROVIDER=true, or "
                "implement the Bedrock providers before deploying with this mode."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Safe to use as a FastAPI dependency."""
    return Settings()
