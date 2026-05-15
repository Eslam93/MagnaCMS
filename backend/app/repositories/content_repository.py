"""Data access for `content_pieces`.

Thin async repository — no business logic, no validation. The service
layer owns parse-fallback orchestration and the user-scoping rules; this
file just shuttles rows between the ORM and the caller.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentPiece


class ContentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, piece: ContentPiece) -> ContentPiece:
        """Insert + flush so the caller gets `id`, `created_at`, and any
        server-side defaults before commit. The caller owns the commit.
        """
        self._session.add(piece)
        await self._session.flush()
        await self._session.refresh(piece)
        return piece

    async def get_for_user(
        self,
        content_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ContentPiece | None:
        """Look up a content piece scoped to its owner.

        Soft-deleted rows are excluded — restoring lives on its own
        endpoint and reads will resurface them then.
        """
        stmt = select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.user_id == user_id,
            ContentPiece.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
