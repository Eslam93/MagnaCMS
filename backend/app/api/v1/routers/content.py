"""/content/* endpoints.

Slice 2 widened POST /content/generate to all four content types. Slice 4
adds the dashboard surface: list, detail, soft delete, and a 24-hour
restore window. The service dispatches generation through its registry;
dashboard reads go through `ContentRepository` directly because there's
no business logic above raw queries.
"""

from __future__ import annotations

import uuid
from math import ceil
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, status
from pydantic import BaseModel

from app.api.v1.deps import CurrentUser
from app.core.exceptions import NotFoundError, ValidationError
from app.core.request_context import get_request_id
from app.db.enums import ContentType
from app.db.session import DbSession
from app.providers.factory import get_llm_provider
from app.repositories.content_repository import ContentRepository
from app.schemas.content import (
    AdCopyResult,
    BlogPostResult,
    ContentDetailResponse,
    ContentListItem,
    ContentListResponse,
    ContentResult,
    EmailResult,
    GenerateRequest,
    GenerateResponse,
    GenerateUsage,
    LinkedInPostResult,
    ListMeta,
    PaginationMeta,
)
from app.services.content_service import ContentService

router = APIRouter(prefix="/content", tags=["content"])

# Storage is open: `result` is JSONB. The router projects the stored
# dict back through the right Pydantic model for the response envelope
# so the OpenAPI contract stays strict per content type.
_RESULT_PROJECTORS: dict[str, type[BaseModel]] = {
    "blog_post": BlogPostResult,
    "linkedin_post": LinkedInPostResult,
    "email": EmailResult,
    "ad_copy": AdCopyResult,
}

# Server-side preview length for the dashboard list. Trimming here keeps
# wire weight bounded and means the FTS hit and the visible preview
# always come from the same string.
_PREVIEW_LEN = 200


def _project_result(
    content_type: str,
    raw: dict[str, Any] | None,
) -> ContentResult | None:
    """Re-validate the stored JSONB against the per-type Pydantic model.

    None passes through — that's the FAILED path where `rendered_text`
    holds the raw model output and `result` was nulled on write.
    """
    if raw is None:
        return None
    model_cls = _RESULT_PROJECTORS[content_type]
    return model_cls.model_validate(raw)  # type: ignore[return-value]


def _build_preview(rendered_text: str) -> str:
    """First `_PREVIEW_LEN` chars of `rendered_text`, with a trailing
    ellipsis when truncated. Newlines pass through; the card flattens
    them at render time.
    """
    if len(rendered_text) <= _PREVIEW_LEN:
        return rendered_text
    return rendered_text[:_PREVIEW_LEN].rstrip() + "…"


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate content (blog post, LinkedIn post, email, or ad copy).",
)
async def generate(
    request: GenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> GenerateResponse:
    """Generate a piece of content for the caller and persist it.

    `request.content_type` must be one of the values the service has a
    registered prompt + renderer for. Pydantic enum validation on the
    request body rejects unknown values with a 422 before this handler
    runs.
    """
    service = ContentService(db, get_llm_provider())
    piece = await service.generate(user=current_user, request=request)
    await db.commit()

    return GenerateResponse(
        content_id=piece.id,
        content_type=piece.content_type,
        result=_project_result(piece.content_type.value, piece.result),
        rendered_text=piece.rendered_text,
        result_parse_status=piece.result_parse_status,
        word_count=piece.word_count or 0,
        usage=GenerateUsage(
            model_id=piece.model_id,
            input_tokens=piece.input_tokens,
            output_tokens=piece.output_tokens,
            cost_usd=piece.cost_usd,
        ),
        created_at=piece.created_at,
    )


@router.get(
    "",
    response_model=ContentListResponse,
    summary="List the caller's content (paginated, with optional filter + search).",
)
async def list_content(
    current_user: CurrentUser,
    db: DbSession,
    content_type: Annotated[ContentType | None, Query(description="Filter by content type")] = None,
    q: Annotated[
        str | None,
        Query(description="Full-text search over rendered_text", max_length=200),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ContentListResponse:
    """Paginated dashboard query — newest first, scoped to the caller,
    soft-deleted rows excluded."""
    repo = ContentRepository(db)
    rows, total = await repo.list_for_user(
        user_id=current_user.id,
        content_type=content_type,
        q=q,
        page=page,
        page_size=page_size,
    )
    total_pages = ceil(total / page_size) if total else 0
    return ContentListResponse(
        data=[
            ContentListItem(
                id=row.id,
                content_type=row.content_type,
                topic=row.topic,
                preview=_build_preview(row.rendered_text),
                word_count=row.word_count or 0,
                model_id=row.model_id,
                result_parse_status=row.result_parse_status,
                created_at=row.created_at,
            )
            for row in rows
        ],
        meta=ListMeta(
            request_id=get_request_id(),
            pagination=PaginationMeta(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        ),
    )


@router.get(
    "/{content_id}",
    response_model=ContentDetailResponse,
    summary="Get one content piece (active rows only).",
)
async def get_content(
    content_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> ContentDetailResponse:
    repo = ContentRepository(db)
    piece = await repo.get_for_user(content_id, current_user.id)
    if piece is None:
        raise NotFoundError("Content not found.", code="CONTENT_NOT_FOUND")
    return ContentDetailResponse(
        id=piece.id,
        content_type=piece.content_type,
        topic=piece.topic,
        tone=piece.tone,
        target_audience=piece.target_audience,
        result=_project_result(piece.content_type.value, piece.result),
        rendered_text=piece.rendered_text,
        result_parse_status=piece.result_parse_status,
        word_count=piece.word_count or 0,
        model_id=piece.model_id,
        created_at=piece.created_at,
        deleted_at=piece.deleted_at,
    )


@router.delete(
    "/{content_id}",
    response_model=ContentDetailResponse,
    summary="Soft-delete the content piece. Restorable for 24 hours.",
)
async def delete_content(
    content_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> ContentDetailResponse:
    repo = ContentRepository(db)
    piece = await repo.soft_delete(content_id, current_user.id)
    if piece is None:
        raise NotFoundError("Content not found.", code="CONTENT_NOT_FOUND")
    await db.commit()
    return ContentDetailResponse(
        id=piece.id,
        content_type=piece.content_type,
        topic=piece.topic,
        tone=piece.tone,
        target_audience=piece.target_audience,
        result=_project_result(piece.content_type.value, piece.result),
        rendered_text=piece.rendered_text,
        result_parse_status=piece.result_parse_status,
        word_count=piece.word_count or 0,
        model_id=piece.model_id,
        created_at=piece.created_at,
        deleted_at=piece.deleted_at,
    )


@router.post(
    "/{content_id}/restore",
    response_model=ContentDetailResponse,
    summary="Restore a soft-deleted content piece (24-hour window).",
)
async def restore_content(
    content_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> ContentDetailResponse:
    repo = ContentRepository(db)
    # Distinguish "no such row" from "outside restore window" by
    # checking the include-deleted lookup first. Both surface to the
    # client as a structured error so the toast can speak in plain
    # terms.
    piece_inc_deleted = await repo.get_for_user_include_deleted(content_id, current_user.id)
    if piece_inc_deleted is None:
        raise NotFoundError("Content not found.", code="CONTENT_NOT_FOUND")
    if piece_inc_deleted.deleted_at is None:
        raise ValidationError(
            "Content is already active.",
            code="CONTENT_NOT_DELETED",
        )

    piece = await repo.restore(content_id, current_user.id)
    if piece is None:
        # The row was deleted but outside the 24-hour window.
        raise ValidationError(
            "Restore window has expired.",
            code="RESTORE_WINDOW_EXPIRED",
        )
    await db.commit()
    return ContentDetailResponse(
        id=piece.id,
        content_type=piece.content_type,
        topic=piece.topic,
        tone=piece.tone,
        target_audience=piece.target_audience,
        result=_project_result(piece.content_type.value, piece.result),
        rendered_text=piece.rendered_text,
        result_parse_status=piece.result_parse_status,
        word_count=piece.word_count or 0,
        model_id=piece.model_id,
        created_at=piece.created_at,
        deleted_at=piece.deleted_at,
    )
