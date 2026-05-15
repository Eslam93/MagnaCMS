"""/content/* endpoints.

Slice 2 widens POST /content/generate to all four content types: blog
post, LinkedIn post, email, ad copy. The service dispatches through its
registry; this router is just the HTTP wrapper.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.api.v1.deps import CurrentUser
from app.db.session import DbSession
from app.providers.factory import get_llm_provider
from app.schemas.content import (
    AdCopyResult,
    BlogPostResult,
    ContentResult,
    EmailResult,
    GenerateRequest,
    GenerateResponse,
    GenerateUsage,
    LinkedInPostResult,
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
