"""Integration tests for the dashboard endpoints.

Covers GET /content (list with pagination + filter + FTS search),
GET /content/{id}, DELETE /content/{id}, and POST /content/{id}/restore.
Uses MockLLMProvider so the test creates rows quickly without hitting
OpenAI; the dashboard CRUD doesn't care which provider generated the
row anyway.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentPiece
from app.providers.factory import reset_provider_cache
from app.providers.llm.mock import MockLLMProvider

# When the dashboard list test asserts strict newest-first ordering by
# `_generate` call sequence, the rows need DISTINCT `created_at`
# values. Postgres `now()` is microsecond-resolution and on fast CI
# runners three sequential mock-LLM API calls can land in the same
# microsecond, which makes the dashboard repository's tiebreaker
# (`ORDER BY created_at DESC, id DESC`, see PR #145) decide ordering
# by random UUID bytes instead of insert order. Forcing a small gap
# between creates is cheaper than adding a serial column to the
# schema and matches real-world usage (humans don't click that fast).
_CREATE_GAP_S = 0.02


@pytest.fixture(autouse=True)
def _force_mock_provider(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "app.api.v1.routers.content.get_llm_provider",
        lambda: MockLLMProvider(),
    )
    reset_provider_cache()


async def _register_and_login(client) -> str:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dashuser@example.com",
            "password": "Secret123",
            "full_name": "Dashboard User",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


async def _generate(client, token, *, content_type="blog_post", topic="Some topic"):  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/content/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": content_type, "topic": topic},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── list ────────────────────────────────────────────────────────────────


async def test_list_returns_paginated_envelope_newest_first(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register_and_login(integration_client)
    first = await _generate(integration_client, token, topic="Topic alpha")
    await asyncio.sleep(_CREATE_GAP_S)
    second = await _generate(integration_client, token, topic="Topic beta")
    await asyncio.sleep(_CREATE_GAP_S)
    third = await _generate(integration_client, token, topic="Topic gamma")

    response = await integration_client.get(
        "/api/v1/content",
        headers={"Authorization": f"Bearer {token}"},
        params={"page": 1, "page_size": 10},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["meta"]["pagination"]["total"] == 3
    assert body["meta"]["pagination"]["page"] == 1
    assert body["meta"]["pagination"]["page_size"] == 10
    assert body["meta"]["pagination"]["total_pages"] == 1
    # Newest-first ordering.
    ids = [item["id"] for item in body["data"]]
    assert ids == [third["content_id"], second["content_id"], first["content_id"]]
    # Preview is non-empty and bounded.
    for item in body["data"]:
        assert item["preview"]
        assert len(item["preview"]) <= 201  # 200 + trailing ellipsis


async def test_list_pagination_walks_pages(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register_and_login(integration_client)
    for i in range(5):
        await _generate(integration_client, token, topic=f"Pagination row {i}")

    page1 = (
        await integration_client.get(
            "/api/v1/content",
            headers={"Authorization": f"Bearer {token}"},
            params={"page": 1, "page_size": 2},
        )
    ).json()
    page2 = (
        await integration_client.get(
            "/api/v1/content",
            headers={"Authorization": f"Bearer {token}"},
            params={"page": 2, "page_size": 2},
        )
    ).json()
    page3 = (
        await integration_client.get(
            "/api/v1/content",
            headers={"Authorization": f"Bearer {token}"},
            params={"page": 3, "page_size": 2},
        )
    ).json()

    assert len(page1["data"]) == 2
    assert len(page2["data"]) == 2
    assert len(page3["data"]) == 1
    assert page1["meta"]["pagination"]["total"] == 5
    assert page1["meta"]["pagination"]["total_pages"] == 3
    # No overlap between pages.
    seen: set[str] = set()
    for page in (page1, page2, page3):
        for item in page["data"]:
            assert item["id"] not in seen
            seen.add(item["id"])


async def test_list_filters_by_content_type(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register_and_login(integration_client)
    blog = await _generate(integration_client, token, content_type="blog_post")
    linkedin = await _generate(integration_client, token, content_type="linkedin_post")
    await _generate(integration_client, token, content_type="email")

    response = await integration_client.get(
        "/api/v1/content",
        headers={"Authorization": f"Bearer {token}"},
        params={"content_type": "blog_post"},
    )
    body = response.json()
    returned_ids = {item["id"] for item in body["data"]}
    assert blog["content_id"] in returned_ids
    assert linkedin["content_id"] not in returned_ids
    for item in body["data"]:
        assert item["content_type"] == "blog_post"


async def test_list_full_text_search_uses_rendered_text(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    """Mock content body contains the word 'mocked'. Searching for it
    must match every generated row; an unrelated term must match
    nothing."""
    token = await _register_and_login(integration_client)
    await _generate(integration_client, token, topic="Topic one")
    await _generate(integration_client, token, topic="Topic two")

    hits = (
        await integration_client.get(
            "/api/v1/content",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": "mocked"},
        )
    ).json()
    assert hits["meta"]["pagination"]["total"] >= 2

    misses = (
        await integration_client.get(
            "/api/v1/content",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": "zzzzunmatchablezzzz"},
        )
    ).json()
    assert misses["meta"]["pagination"]["total"] == 0


async def test_list_scoped_to_caller(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    """Two users; each only sees their own rows."""
    # First user generates 2.
    response = await integration_client.post(
        "/api/v1/auth/register",
        json={"email": "u1@example.com", "password": "Secret123", "full_name": "User One"},
    )
    token1 = response.json()["access_token"]
    await _generate(integration_client, token1)
    await _generate(integration_client, token1)

    # Second user — no rows.
    response = await integration_client.post(
        "/api/v1/auth/register",
        json={"email": "u2@example.com", "password": "Secret123", "full_name": "User Two"},
    )
    token2 = response.json()["access_token"]

    own = (
        await integration_client.get(
            "/api/v1/content",
            headers={"Authorization": f"Bearer {token1}"},
        )
    ).json()
    assert own["meta"]["pagination"]["total"] == 2

    other = (
        await integration_client.get(
            "/api/v1/content",
            headers={"Authorization": f"Bearer {token2}"},
        )
    ).json()
    assert other["meta"]["pagination"]["total"] == 0


async def test_list_requires_authentication(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    response = await integration_client.get("/api/v1/content")
    assert response.status_code == 401


# ── detail ──────────────────────────────────────────────────────────────


async def test_detail_returns_full_payload(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register_and_login(integration_client)
    generated = await _generate(integration_client, token)

    response = await integration_client.get(
        f"/api/v1/content/{generated['content_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == generated["content_id"]
    assert body["content_type"] == "blog_post"
    assert body["rendered_text"]
    assert body["result"] is not None
    assert body["deleted_at"] is None


async def test_detail_returns_404_for_unknown_id(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register_and_login(integration_client)
    response = await integration_client.get(
        "/api/v1/content/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONTENT_NOT_FOUND"


async def test_detail_returns_404_for_other_users_row(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    response = await integration_client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "Secret123", "full_name": "Owner"},
    )
    owner_token = response.json()["access_token"]
    generated = await _generate(integration_client, owner_token)

    response = await integration_client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "Secret123", "full_name": "Other"},
    )
    other_token = response.json()["access_token"]
    response = await integration_client.get(
        f"/api/v1/content/{generated['content_id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


# ── delete + restore ────────────────────────────────────────────────────


async def test_delete_then_restore_round_trip(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register_and_login(integration_client)
    generated = await _generate(integration_client, token)
    content_id = generated["content_id"]

    deleted = await integration_client.delete(
        f"/api/v1/content/{content_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_at"] is not None

    # Soft-deleted row drops out of the list.
    listed = (
        await integration_client.get(
            "/api/v1/content",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()
    assert all(item["id"] != content_id for item in listed["data"])

    # Detail returns 404 for the soft-deleted id.
    detail_resp = await integration_client.get(
        f"/api/v1/content/{content_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_resp.status_code == 404

    # Restore brings it back.
    restored = await integration_client.post(
        f"/api/v1/content/{content_id}/restore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["deleted_at"] is None

    relisted = (
        await integration_client.get(
            "/api/v1/content",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()
    assert any(item["id"] == content_id for item in relisted["data"])


async def test_delete_returns_404_for_unknown_id(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register_and_login(integration_client)
    response = await integration_client.delete(
        "/api/v1/content/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


async def test_restore_returns_validation_error_when_not_deleted(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register_and_login(integration_client)
    generated = await _generate(integration_client, token)
    response = await integration_client.post(
        f"/api/v1/content/{generated['content_id']}/restore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTENT_NOT_DELETED"


async def test_restore_outside_24h_window_returns_validation_error(
    integration_client,  # type: ignore[no-untyped-def]
    db_session: AsyncSession,
) -> None:
    """Push `deleted_at` back 25 hours and confirm the restore is
    rejected with the structured RESTORE_WINDOW_EXPIRED code."""
    token = await _register_and_login(integration_client)
    generated = await _generate(integration_client, token)
    content_id = generated["content_id"]

    # First soft-delete via the API.
    await integration_client.delete(
        f"/api/v1/content/{content_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Now reach into the DB to age the deletion timestamp past the window.
    stmt = select(ContentPiece).where(ContentPiece.id == content_id)
    row = (await db_session.execute(stmt)).scalar_one()
    row.deleted_at = datetime.now(UTC) - timedelta(hours=25)
    await db_session.flush()

    response = await integration_client.post(
        f"/api/v1/content/{content_id}/restore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESTORE_WINDOW_EXPIRED"
