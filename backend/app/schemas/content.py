"""Pydantic request / response schemas for /content/* endpoints.

Slice 1 ships blog-post generation only. The request body and the response
envelope are typed for every supported content type from day one, so adding
LinkedIn / email / ad-copy in Slice 2 is a Pydantic-only change — no route
signature churn. Each per-type result model is a strict validator: the
content service runs the LLM output through it and the three-stage parse
fallback (parse → retry → degrade) keys off Pydantic ValidationError.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import ContentType, ResultParseStatus

# ── Request ────────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    """Body for POST /content/generate.

    `content_type` is open to every value in the enum so the schema can
    cover future slices, but the router rejects anything except
    BLOG_POST in Slice 1 with a 400. That validation lives in the
    router, not here, to keep the schema slice-agnostic.
    """

    content_type: ContentType
    topic: Annotated[str, Field(min_length=3, max_length=500)]
    tone: Annotated[str | None, Field(default=None, max_length=120)] = None
    target_audience: Annotated[str | None, Field(default=None, max_length=500)] = None
    brand_voice_id: uuid.UUID | None = None


# ── Per-type result models ─────────────────────────────────────────────


class BlogPostSection(BaseModel):
    heading: Annotated[str, Field(min_length=1)]
    body: Annotated[str, Field(min_length=1)]


class BlogPostResult(BaseModel):
    """Structured shape the blog-post prompt asks the model to return.

    Mirrors §7.1 of PROJECT_BRIEF.md. `model_config` forbids extras so
    a model that returns the right keys plus garbage triggers the retry
    path rather than silently passing through.
    """

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=200)]
    meta_description: Annotated[str, Field(min_length=1, max_length=160)]
    intro: Annotated[str, Field(min_length=1)]
    sections: Annotated[list[BlogPostSection], Field(min_length=1)]
    conclusion: Annotated[str, Field(min_length=1)]
    suggested_tags: Annotated[list[str], Field(min_length=1, max_length=10)]


# ── Response ───────────────────────────────────────────────────────────


class GenerateUsage(BaseModel):
    """Per-call usage block. Same shape across content types."""

    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class GenerateResponse(BaseModel):
    """Body for POST /content/generate.

    `result` is None when `result_parse_status == FAILED` — the frontend
    falls back to `rendered_text`, which always carries something
    usable (model output verbatim in the failed case).
    """

    content_id: uuid.UUID
    content_type: ContentType
    result: BlogPostResult | None
    rendered_text: str
    result_parse_status: ResultParseStatus
    word_count: int
    usage: GenerateUsage
    created_at: datetime


# Re-exports keep the per-slice surface tidy: any future slice that
# adds LinkedIn / email / ad-copy result models can append to this list
# and update the `GenerateResponse.result` union without touching call
# sites that import the schema name.
__all__ = [
    "BlogPostResult",
    "BlogPostSection",
    "ContentType",
    "GenerateRequest",
    "GenerateResponse",
    "GenerateUsage",
    "ResultParseStatus",
]
