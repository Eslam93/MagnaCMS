"""Tests for the Origin-based CSRF guard.

The middleware protects cookie-only POST endpoints from cross-origin
requests when the refresh cookie is `SameSite=none`. Bearer-authed
endpoints (everything else under /api/v1/*) are intentionally skipped.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_refresh_with_disallowed_origin_returns_403() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={
                "origin": "https://evil.example.com",
                "sec-fetch-site": "cross-site",
            },
        )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "CSRF_ORIGIN_REJECTED"
    assert "evil.example.com" in body["error"]["details"]["reason"]


@pytest.mark.asyncio
async def test_refresh_with_no_origin_passes_through() -> None:
    """Server-to-server callers (curl, k8s probes) never send Origin.
    The guard must let them through — the refresh endpoint's own
    auth check (missing-cookie 401) is the next gate.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/auth/refresh")
    # No Origin → middleware passes; route handler then 401s because
    # there's no refresh cookie. The point is we don't 403.
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_refresh_with_same_origin_sec_fetch_passes() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={
                "origin": "https://anywhere.example.com",
                "sec-fetch-site": "same-origin",
            },
        )
    # Sec-Fetch-Site: same-origin overrides the unknown Origin.
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_refresh_with_allowlisted_origin_passes() -> None:
    # The default cors_origins includes http://localhost:3000 in local
    # env, which is where the test suite runs.
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={
                "origin": "http://localhost:3000",
                "sec-fetch-site": "cross-site",
            },
        )
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_unprotected_endpoint_with_disallowed_origin_passes() -> None:
    """Only the cookie-only routes are guarded. Bearer-authed endpoints
    don't expose this CSRF surface — their access token isn't auto-
    attached from an attacker origin."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/health",
            headers={"origin": "https://evil.example.com"},
        )
    assert response.status_code == 200
