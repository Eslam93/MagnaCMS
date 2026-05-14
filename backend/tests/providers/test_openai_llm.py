"""OpenAIChatProvider — retry, cost, structured-output, error mapping.

We never hit the real API in tests. The openai SDK exposes
`AsyncOpenAI(...).chat.completions.create` which we stub by injecting
a fake client into the provider constructor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from app.providers.errors import ProviderError, ProviderRetryExhausted
from app.providers.llm.openai_provider import OpenAIChatProvider, _compute_cost_usd

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def _build_fake_response(
    *,
    content: str,
    model: str = "gpt-5.4-mini-2026-03-17",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    finish_reason: str = "stop",
) -> MagicMock:
    """Construct an object that quacks like the openai SDK's
    ChatCompletion response — enough fields for our provider to read."""
    response = MagicMock()
    response.model = model
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = finish_reason
    response.usage = MagicMock()
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    return response


def _build_fake_client(create_mock: AsyncMock) -> MagicMock:
    """Wire `client.chat.completions.create` to `create_mock`."""
    client = MagicMock()
    client.chat.completions.create = create_mock
    return client


# ── cost calculation ───────────────────────────────────────────────────


def test_compute_cost_usd_for_known_model() -> None:
    # 1000 input + 500 output at $0.15/$0.60 per 1M.
    cost = _compute_cost_usd("gpt-5.4-mini-2026-03-17", 1000, 500)
    assert cost == pytest.approx((1000 * 0.15 + 500 * 0.60) / 1_000_000)


def test_compute_cost_usd_for_unknown_model_returns_zero() -> None:
    # Unknown models log a warning but don't crash.
    assert _compute_cost_usd("future-model-not-priced", 1000, 500) == 0.0


# ── happy path ─────────────────────────────────────────────────────────


async def test_generate_returns_parsed_result(monkeypatch: MonkeyPatch) -> None:
    """A single successful call returns an LLMResult with the response
    body, model, tokens, cost, latency, and finish_reason populated."""
    create_mock = AsyncMock(return_value=_build_fake_response(content='{"x": 1}'))
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client, model="gpt-5.4-mini-2026-03-17")

    result = await provider.generate(
        system_prompt="sys",
        user_prompt="user",
        content_type="blog_post",
    )
    assert result.raw_text == '{"x": 1}'
    assert result.model == "gpt-5.4-mini-2026-03-17"
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.cost_usd > 0
    assert result.finish_reason == "stop"


async def test_generate_passes_json_schema_when_supplied() -> None:
    """When `json_schema` is set, the SDK call must include the
    structured-output `response_format`."""
    create_mock = AsyncMock(return_value=_build_fake_response(content="{}"))
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client)

    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    await provider.generate(
        system_prompt="s",
        user_prompt="u",
        json_schema=schema,
        content_type="blog_post",
    )
    kwargs = create_mock.call_args.kwargs
    assert "response_format" in kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert kwargs["response_format"]["json_schema"]["schema"] == schema


async def test_generate_omits_response_format_when_schema_is_none() -> None:
    """Free-form generation must not request structured output —
    response_format would force JSON the caller didn't ask for."""
    create_mock = AsyncMock(return_value=_build_fake_response(content="hello"))
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client)

    await provider.generate(
        system_prompt="s",
        user_prompt="u",
        content_type="blog_post",
    )
    kwargs = create_mock.call_args.kwargs
    assert "response_format" not in kwargs


# ── retry behavior ─────────────────────────────────────────────────────


def _make_retryable_error() -> openai.RateLimitError:
    """Construct a RateLimitError with the minimum args the SDK requires."""
    return openai.RateLimitError(
        message="rate limited",
        response=MagicMock(status_code=429, headers={}),
        body={"error": "rate_limit"},
    )


async def test_retries_on_rate_limit_and_succeeds(
    monkeypatch: MonkeyPatch,
) -> None:
    """First call returns 429, second succeeds — provider must retry."""
    # No real sleeping in tests.
    monkeypatch.setattr("app.providers.llm.openai_provider.asyncio.sleep", AsyncMock())

    create_mock = AsyncMock(
        side_effect=[
            _make_retryable_error(),
            _build_fake_response(content="ok"),
        ]
    )
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client, max_retries=3)

    result = await provider.generate(
        system_prompt="s",
        user_prompt="u",
        content_type="blog_post",
    )
    assert result.raw_text == "ok"
    assert create_mock.call_count == 2


async def test_retries_exhausted_raises_retry_exhausted(
    monkeypatch: MonkeyPatch,
) -> None:
    """When every attempt raises a retryable error, the provider gives
    up with `ProviderRetryExhausted`."""
    monkeypatch.setattr("app.providers.llm.openai_provider.asyncio.sleep", AsyncMock())

    create_mock = AsyncMock(side_effect=[_make_retryable_error()] * 3)
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client, max_retries=3)

    with pytest.raises(ProviderRetryExhausted):
        await provider.generate(
            system_prompt="s",
            user_prompt="u",
            content_type="blog_post",
        )
    assert create_mock.call_count == 3


async def test_non_retryable_error_raises_provider_error() -> None:
    """Auth errors, bad requests, content_filter — none of these should
    be retried. The provider raises `ProviderError` immediately."""

    class _AuthError(openai.AuthenticationError):
        def __init__(self) -> None:
            super().__init__(
                message="bad key",
                response=MagicMock(status_code=401, headers={}),
                body={"error": "invalid_api_key"},
            )

    create_mock = AsyncMock(side_effect=_AuthError())
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client, max_retries=3)

    with pytest.raises(ProviderError):
        await provider.generate(
            system_prompt="s",
            user_prompt="u",
            content_type="blog_post",
        )
    # No retries on non-retryable errors.
    assert create_mock.call_count == 1


# ── backoff math ───────────────────────────────────────────────────────


def test_backoff_grows_exponentially() -> None:
    """Successive attempts should sleep ~1, ~2, ~4 seconds plus jitter."""
    s1 = OpenAIChatProvider._backoff_seconds(1)
    s2 = OpenAIChatProvider._backoff_seconds(2)
    s3 = OpenAIChatProvider._backoff_seconds(3)
    # Bases are 1, 2, 4. Jitter adds up to +25% of base.
    assert 1.0 <= s1 < 1.25
    assert 2.0 <= s2 < 2.50
    assert 4.0 <= s3 < 5.00


# ── config error path ─────────────────────────────────────────────────


def test_construction_without_api_key_raises_config_error(monkeypatch: MonkeyPatch) -> None:
    """Provider construction must fail fast when no API key is configured."""
    from app.core.config import get_settings

    settings = get_settings()
    # Force the cached settings to look as if no key is set.
    monkeypatch.setattr(settings, "openai_api_key", None)
    from app.providers.errors import ProviderConfigError

    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        OpenAIChatProvider()


# Silence unused-import lint when imports above are only used for types.
_ = Any
