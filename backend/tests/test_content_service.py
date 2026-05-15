"""Unit tests for the three-stage parse fallback in ContentService.

The service is exercised end-to-end against a real test session in
`tests/integration/test_content_routes.py`. This file uses fake
providers + in-memory factories to lock the fallback semantics without
spinning up Postgres.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.db.enums import ResultParseStatus
from app.providers.llm.base import LLMResult
from app.schemas.content import GenerateRequest
from app.services.content_service import ContentService

# ── fakes ──────────────────────────────────────────────────────────────


@dataclass
class _RecordingSession:
    """Bare-minimum async-session stand-in.

    The service calls `add → flush → refresh` on the session via the
    repo. We capture the added row, no-op flush/refresh, and let the
    test assert on what was persisted.
    """

    added: list[Any] | None = None

    def __post_init__(self) -> None:
        self.added = []

    def add(self, obj: Any) -> None:
        assert self.added is not None
        self.added.append(obj)

    async def flush(self) -> None:
        # Mimic Postgres assigning defaults — fill in word_count etc. is
        # already done by the service; nothing to do here.
        return None

    async def refresh(self, obj: Any) -> None:
        return None


def _fake_provider(raw_texts: list[str]) -> AsyncMock:
    """Build an AsyncMock provider whose `.generate(...)` returns the
    given raw_texts in order.

    Each call records token usage so we can verify the service sums
    them across attempts.
    """
    results = [
        LLMResult(
            raw_text=raw,
            model="fake-model-v0",
            input_tokens=5,
            output_tokens=7,
            cost_usd=0.01,
            latency_ms=1,
            finish_reason="stop",
        )
        for raw in raw_texts
    ]
    mock = AsyncMock()
    mock.generate.side_effect = results
    return mock


_VALID_BLOG_JSON = json.dumps(
    {
        "title": "Mocks in CI",
        "meta_description": "A short explanation.",
        "intro": "Why we mock.",
        "sections": [{"heading": "H", "body": "B"}],
        "conclusion": "Done.",
        "suggested_tags": ["mock"],
    }
)


def _request() -> GenerateRequest:
    return GenerateRequest(
        content_type="blog_post",  # type: ignore[arg-type]
        topic="A topic for testing",
        tone="informative",
        target_audience="engineers",
    )


# ── tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_attempt_1_success_status_ok() -> None:
    session = _RecordingSession()
    provider = _fake_provider([_VALID_BLOG_JSON])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    user = type("U", (), {"id": "00000000-0000-0000-0000-000000000001"})()
    piece = await service.generate_blog_post(user=user, request=_request())  # type: ignore[arg-type]

    assert piece.result_parse_status == ResultParseStatus.OK
    assert piece.result is not None
    assert piece.rendered_text.startswith("# Mocks in CI")
    assert provider.generate.await_count == 1
    assert piece.input_tokens == 5
    assert piece.output_tokens == 7
    assert piece.cost_usd == Decimal("0.01")


@pytest.mark.asyncio
async def test_attempt_2_corrective_retry_status_retried() -> None:
    session = _RecordingSession()
    provider = _fake_provider(["not json at all", _VALID_BLOG_JSON])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    user = type("U", (), {"id": "00000000-0000-0000-0000-000000000001"})()
    piece = await service.generate_blog_post(user=user, request=_request())  # type: ignore[arg-type]

    assert piece.result_parse_status == ResultParseStatus.RETRIED
    assert piece.result is not None
    # Both calls' tokens summed.
    assert piece.input_tokens == 10
    assert piece.output_tokens == 14
    assert piece.cost_usd == Decimal("0.02")
    # Retry call should not pass json_schema (per service contract).
    _, second_kwargs = provider.generate.call_args_list[1]
    assert second_kwargs["json_schema"] is None


@pytest.mark.asyncio
async def test_attempt_3_graceful_degrade_status_failed() -> None:
    session = _RecordingSession()
    provider = _fake_provider(["{bad json", "still bad"])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    user = type("U", (), {"id": "00000000-0000-0000-0000-000000000001"})()
    piece = await service.generate_blog_post(user=user, request=_request())  # type: ignore[arg-type]

    assert piece.result_parse_status == ResultParseStatus.FAILED
    assert piece.result is None
    # Raw model output preserved so the frontend has something to show.
    assert piece.rendered_text == "still bad"
    # Both calls still summed for cost accounting.
    assert piece.input_tokens == 10
    assert piece.output_tokens == 14


@pytest.mark.asyncio
async def test_valid_json_wrong_schema_falls_through_to_retry() -> None:
    """A response that's valid JSON but fails Pydantic validation must
    trigger the retry path — schema-conforming output is non-negotiable.
    """
    session = _RecordingSession()
    wrong_shape = json.dumps({"this_is_not": "a blog post"})
    provider = _fake_provider([wrong_shape, _VALID_BLOG_JSON])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    user = type("U", (), {"id": "00000000-0000-0000-0000-000000000001"})()
    piece = await service.generate_blog_post(user=user, request=_request())  # type: ignore[arg-type]

    assert piece.result_parse_status == ResultParseStatus.RETRIED
    assert piece.result is not None


@pytest.mark.asyncio
async def test_prompt_snapshot_persisted_even_on_failure() -> None:
    session = _RecordingSession()
    provider = _fake_provider(["bad", "still bad"])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    user = type("U", (), {"id": "00000000-0000-0000-0000-000000000001"})()
    piece = await service.generate_blog_post(user=user, request=_request())  # type: ignore[arg-type]

    assert piece.system_prompt_snapshot
    assert piece.user_prompt_snapshot
    assert piece.prompt_version == "blog_post.v1"
