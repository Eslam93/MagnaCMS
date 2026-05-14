"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An httpx AsyncClient bound directly to the ASGI app (in-process)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
