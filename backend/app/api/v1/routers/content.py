"""/content/* endpoints.

Slice 1 ships POST /content/generate for blog posts only. The schema
already covers every content type so Slice 2 (LinkedIn, email,
ad-copy) is a router branch + new prompt module, no shape changes.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.v1.deps import CurrentUser
from app.core.exceptions import ValidationError
from app.db.enums import ContentType
from app.db.session import DbSession
from app.providers.factory import get_llm_provider
from app.schemas.content import (
    BlogPostResult,
    GenerateRequest,
    GenerateResponse,
    GenerateUsage,
)
from app.services.content_service import ContentService

router = APIRouter(prefix="/content", tags=["content"])

# Content types the live router accepts today. Anything else in the
# `ContentType` enum returns 422 with a slice-aware message so the
# frontend can keep showing the same form across slices.
_SUPPORTED_CONTENT_TYPES_SLICE_1: frozenset[ContentType] = frozenset({ContentType.BLOG_POST})


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate content (Slice 1: blog post only).",
)
async def generate(
    request: GenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> GenerateResponse:
    """Generate a piece of content for the caller and persist it.

    The response is the same envelope every slice will use; the only
    thing widening over time is the set of accepted `content_type`s.
    """
    if request.content_type not in _SUPPORTED_CONTENT_TYPES_SLICE_1:
        raise ValidationError(
            f"content_type={request.content_type.value!r} is not yet supported. "
            "Slice 1 ships blog_post only; LinkedIn, email, and ad copy arrive in Slice 2.",
            code="UNSUPPORTED_CONTENT_TYPE",
        )

    service = ContentService(db, get_llm_provider())
    piece = await service.generate_blog_post(user=current_user, request=request)
    await db.commit()

    # `piece.result` is `dict | None` (JSONB on the model) so reconstruct
    # the typed Pydantic shape for the response. `BlogPostResult` keeps
    # the response strict even though the storage column is open.
    result_payload: BlogPostResult | None = (
        BlogPostResult.model_validate(piece.result) if piece.result is not None else None
    )

    return GenerateResponse(
        content_id=piece.id,
        content_type=piece.content_type,
        result=result_payload,
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
