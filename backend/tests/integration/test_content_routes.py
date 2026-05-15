"""Integration tests for POST /api/v1/content/generate.

Uses MockLLMProvider end-to-end so the tests don't reach out to OpenAI.
The real OpenAIChatProvider has unit coverage at
`tests/providers/test_openai_llm.py`; this file proves the route +
service + repository wire together against a real Postgres.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ContentType, ResultParseStatus
from app.db.models import ContentPiece
from app.providers.factory import reset_provider_cache
from app.providers.llm.mock import MockLLMProvider


async def _register_and_login(integration_client) -> str:  # type: ignore[no-untyped-def]
    """Register a user and return a Bearer-ready access token."""
    response = await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "writer@example.com",
            "password": "Secret123",
            "full_name": "Writer Example",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


async def test_generate_blog_post_with_mock_returns_full_response(
    integration_client,  # type: ignore[no-untyped-def]
    db_session: AsyncSession,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """End-to-end happy path against MockLLMProvider.

    Mocks `get_llm_provider` so the test forces the mock provider
    regardless of `AI_PROVIDER_MODE` in the test env. Asserts the
    response envelope shape, the persisted row, and the parse-status
    semantics.
    """
    monkeypatch.setattr(
        "app.api.v1.routers.content.get_llm_provider",
        lambda: MockLLMProvider(),
    )
    reset_provider_cache()

    token = await _register_and_login(integration_client)

    response = await integration_client.post(
        "/api/v1/content/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "content_type": "blog_post",
            "topic": "Mocked content for local development",
            "tone": "informative",
            "target_audience": "engineers",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["content_type"] == "blog_post"
    assert body["result_parse_status"] == "ok"
    assert body["word_count"] > 0
    assert body["rendered_text"].startswith("# ")  # markdown title
    assert "## " in body["rendered_text"]  # at least one H2
    assert body["result"]["title"]
    assert body["result"]["sections"]
    assert body["usage"]["model_id"] == "mock-llm-v1"
    # Mock provider returns zero-cost. Decimal serializes as string.
    assert body["usage"]["cost_usd"] in ("0", "0.000000")

    # DB row exists, owned by the registered user.
    content_id = body["content_id"]
    stmt = select(ContentPiece).where(ContentPiece.id == content_id)
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.content_type == ContentType.BLOG_POST
    assert row.result_parse_status == ResultParseStatus.OK
    assert row.prompt_version == "blog_post.v1"
    assert row.system_prompt_snapshot
    assert row.user_prompt_snapshot
    assert row.result is not None
    assert row.rendered_text == body["rendered_text"]


async def test_generate_requires_authentication(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    response = await integration_client.post(
        "/api/v1/content/generate",
        json={
            "content_type": "blog_post",
            "topic": "Anything",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] in {"MISSING_TOKEN", "INVALID_TOKEN"}


async def test_generate_rejects_unsupported_content_type_in_slice_1(
    integration_client,  # type: ignore[no-untyped-def]
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """Slice 2 will widen this — for now, only blog_post is accepted."""
    monkeypatch.setattr(
        "app.api.v1.routers.content.get_llm_provider",
        lambda: MockLLMProvider(),
    )
    reset_provider_cache()

    token = await _register_and_login(integration_client)
    response = await integration_client.post(
        "/api/v1/content/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "content_type": "linkedin_post",
            "topic": "Hello",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_CONTENT_TYPE"


async def test_generate_validates_request_body(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register_and_login(integration_client)
    response = await integration_client.post(
        "/api/v1/content/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "content_type": "blog_post",
            "topic": "x",  # min_length=3 fails
        },
    )
    assert response.status_code == 422
