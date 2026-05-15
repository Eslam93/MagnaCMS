"""Async SQLAlchemy engine, session factory, and FastAPI dependency.

The engine and sessionmaker are lazy singletons — created on first use so
that test environments can override settings before either is materialized.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first call.

    Pool sizing aims to cover the App Runner instance's default
    MaxConcurrency=100 without forcing every request to queue on the
    DB. `pool_size=15, max_overflow=20` → 35 max concurrent
    connections per instance. Image generation no longer holds a
    connection across upstream calls (see `image_service` + the
    `NOWAIT` lock in `ContentRepository.get_for_user`), so 35 is
    comfortable headroom — and RDS `db.t4g.micro` defaults to
    `max_connections ≈ 87`, so a min=1/max=3 App Runner fleet still
    leaves room for psql sessions + migrations.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=15,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency.

    Yields one `AsyncSession` per request. Commits on clean exit, rolls back
    on exception. The session is closed by the async context manager either way.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def check_db_health() -> bool:
    """Cheap reachability probe — `SELECT 1`. Returns False on any failure."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        log.warning("db_health_check_failed", error=str(exc))
        return False
    return True


async def close_db_engine() -> None:
    """Dispose the engine. Call on app shutdown to release pool connections."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
