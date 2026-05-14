"""Tests for the /api/v1/health endpoint."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "environment" in body
    assert "dependencies" in body
    assert set(body["dependencies"].keys()) == {"db", "redis", "openai"}


async def test_health_echoes_incoming_request_id(client: AsyncClient) -> None:
    incoming = "11111111-2222-3333-4444-555555555555"
    response = await client.get(
        "/api/v1/health",
        headers={"X-Request-ID": incoming},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == incoming


async def test_health_generates_request_id_when_absent(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    # uuid4 stringified is 36 chars (32 hex + 4 dashes)
    assert len(request_id) == 36
