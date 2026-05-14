"""OpenAIImageProvider — retry, cost, b64 decode, error mapping."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from app.providers.errors import ProviderError, ProviderRetryExhausted
from app.providers.image.base import ImageQuality
from app.providers.image.openai_provider import OpenAIImageProvider, _compute_cost_usd

if TYPE_CHECKING:
    from pytest import MonkeyPatch


# A 1×1 transparent PNG, the same one MockImageProvider uses.
_FAKE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6"
    "kgAAAABJRU5ErkJggg=="
)


def _build_fake_image_response(b64: str = _FAKE_PNG_B64) -> MagicMock:
    response = MagicMock()
    response.data = [MagicMock()]
    response.data[0].b64_json = b64
    return response


def _build_fake_client(generate_mock: AsyncMock) -> MagicMock:
    client = MagicMock()
    client.images.generate = generate_mock
    return client


def _make_rate_limit_error() -> openai.RateLimitError:
    return openai.RateLimitError(
        message="rate limited",
        response=MagicMock(status_code=429, headers={}),
        body={"error": "rate_limit"},
    )


# ── cost ───────────────────────────────────────────────────────────────


def test_cost_for_each_known_quality() -> None:
    assert _compute_cost_usd("gpt-image-1", ImageQuality.LOW) == 0.011
    assert _compute_cost_usd("gpt-image-1", ImageQuality.MEDIUM) == 0.042
    assert _compute_cost_usd("gpt-image-1", ImageQuality.HIGH) == 0.167


def test_cost_for_unknown_model_is_zero() -> None:
    assert _compute_cost_usd("future-image-model", ImageQuality.HIGH) == 0.0


# ── happy path ─────────────────────────────────────────────────────────


async def test_generate_returns_image_bytes_and_metadata() -> None:
    generate_mock = AsyncMock(return_value=_build_fake_image_response())
    client = _build_fake_client(generate_mock)
    provider = OpenAIImageProvider(client=client, model="gpt-image-1")

    result = await provider.generate(prompt="a cat", quality=ImageQuality.LOW)
    assert result.image_bytes == base64.b64decode(_FAKE_PNG_B64)
    assert result.model == "gpt-image-1"
    assert result.quality == ImageQuality.LOW
    assert result.cost_usd == 0.011
    assert result.width == 1024
    assert result.height == 1024
    assert result.prompt_used == "a cat"


async def test_generate_passes_quality_and_size_to_sdk() -> None:
    generate_mock = AsyncMock(return_value=_build_fake_image_response())
    client = _build_fake_client(generate_mock)
    provider = OpenAIImageProvider(client=client, model="gpt-image-1")

    await provider.generate(prompt="x", quality=ImageQuality.HIGH, size=(1024, 1024))
    kwargs = generate_mock.call_args.kwargs
    assert kwargs["quality"] == "high"
    assert kwargs["size"] == "1024x1024"
    assert kwargs["n"] == 1


# ── error paths ────────────────────────────────────────────────────────


async def test_response_with_no_data_raises_provider_error() -> None:
    """Defensive coverage — if OpenAI ever returns an empty `data` array,
    we surface a clear ProviderError instead of an IndexError."""
    empty = MagicMock()
    empty.data = []
    generate_mock = AsyncMock(return_value=empty)
    client = _build_fake_client(generate_mock)
    provider = OpenAIImageProvider(client=client, model="gpt-image-1")

    with pytest.raises(ProviderError, match="no data"):
        await provider.generate(prompt="x")


async def test_response_with_missing_b64_raises_provider_error() -> None:
    fake = MagicMock()
    fake.data = [MagicMock()]
    fake.data[0].b64_json = None
    generate_mock = AsyncMock(return_value=fake)
    client = _build_fake_client(generate_mock)
    provider = OpenAIImageProvider(client=client, model="gpt-image-1")

    with pytest.raises(ProviderError, match="b64_json"):
        await provider.generate(prompt="x")


# ── retry behavior ─────────────────────────────────────────────────────


async def test_retries_on_rate_limit_and_succeeds(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("app.providers.image.openai_provider.asyncio.sleep", AsyncMock())

    generate_mock = AsyncMock(side_effect=[_make_rate_limit_error(), _build_fake_image_response()])
    client = _build_fake_client(generate_mock)
    provider = OpenAIImageProvider(client=client, model="gpt-image-1", max_retries=3)

    result = await provider.generate(prompt="x")
    assert generate_mock.call_count == 2
    assert result.image_bytes


async def test_retries_exhausted_raises(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("app.providers.image.openai_provider.asyncio.sleep", AsyncMock())

    generate_mock = AsyncMock(side_effect=[_make_rate_limit_error()] * 3)
    client = _build_fake_client(generate_mock)
    provider = OpenAIImageProvider(client=client, model="gpt-image-1", max_retries=3)

    with pytest.raises(ProviderRetryExhausted):
        await provider.generate(prompt="x")
    assert generate_mock.call_count == 3


async def test_construction_without_api_key_raises_config_error(
    monkeypatch: MonkeyPatch,
) -> None:
    from app.core.config import get_settings
    from app.providers.errors import ProviderConfigError

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", None)
    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        OpenAIImageProvider()
