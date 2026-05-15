"""Content generation orchestration.

Slice 1 supports blog-post only; the router enforces that and this file
wires the blog-post prompt module + result schema + renderer through the
three-stage parse fallback.

The fallback is non-negotiable (PROJECT_BRIEF §7.0):

  1. Attempt 1 — call provider with strict json_schema. Pydantic-validate.
                 Status = OK on success.
  2. Attempt 2 — on parse/validation failure, re-call without json_schema,
                 appending a corrective instruction. Status = RETRIED on
                 success.
  3. Attempt 3 — on second failure, persist the raw model output as
                 `rendered_text` with `result = None`,
                 `result_parse_status = FAILED`. Sentry-warn so we notice
                 drift without crashing the user.

Aggregate token usage from both calls; cost is the sum of both
`LLMResult.cost_usd` values (zero for mock).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.enums import ContentType, ResultParseStatus
from app.db.models import ContentPiece, User
from app.prompts.blog_post import (
    CORRECTIVE_RETRY_INSTRUCTION,
)
from app.prompts.blog_post import (
    JSON_SCHEMA as BLOG_POST_JSON_SCHEMA,
)
from app.prompts.blog_post import (
    PROMPT_VERSION as BLOG_POST_PROMPT_VERSION,
)
from app.prompts.blog_post import (
    build_prompt as build_blog_post_prompt,
)
from app.providers.llm.base import ILLMProvider, LLMResult
from app.repositories.content_repository import ContentRepository
from app.schemas.content import BlogPostResult, GenerateRequest

log = get_logger(__name__)


@dataclass(frozen=True)
class _ParseOutcome:
    """Internal result of the three-stage parse pass.

    Either `result` is populated (OK or RETRIED — `rendered_text` is the
    markdown render of `result`), or it's None (FAILED — `rendered_text`
    is the raw model output verbatim).
    """

    result: BlogPostResult | None
    rendered_text: str
    status: ResultParseStatus


class ContentService:
    """Generate content. One public method; everything else is helper."""

    def __init__(self, session: AsyncSession, provider: ILLMProvider) -> None:
        self._session = session
        self._provider = provider
        self._repo = ContentRepository(session)

    async def generate_blog_post(
        self,
        *,
        user: User,
        request: GenerateRequest,
    ) -> ContentPiece:
        """Run the prompt → parse → persist pipeline. Returns the inserted row.

        The caller commits the transaction. Service-layer code is
        unaware of the FastAPI request envelope; the router handles that.
        """
        from app.services.renderers import render_blog_post, word_count

        system_prompt, user_prompt = build_blog_post_prompt(
            topic=request.topic,
            tone=request.tone,
            target_audience=request.target_audience,
        )

        # --- Attempt 1: strict json_schema ---
        attempt1 = await self._provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=BLOG_POST_JSON_SCHEMA["schema"],
            content_type=ContentType.BLOG_POST.value,
        )
        outcome = self._try_parse(attempt1.raw_text, ResultParseStatus.OK)

        total_input = attempt1.input_tokens
        total_output = attempt1.output_tokens
        total_cost = Decimal(str(attempt1.cost_usd))
        model_id = attempt1.model

        # --- Attempt 2: corrective retry ---
        if outcome.result is None:
            log.warning(
                "blog_post_parse_failed_attempt_1",
                user_id=str(user.id),
                model=model_id,
            )
            attempt2 = await self._call_corrective_retry(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                previous_raw=attempt1.raw_text,
            )
            outcome = self._try_parse(attempt2.raw_text, ResultParseStatus.RETRIED)
            total_input += attempt2.input_tokens
            total_output += attempt2.output_tokens
            total_cost += Decimal(str(attempt2.cost_usd))

            if outcome.result is None:
                # Stage 3 — graceful degrade. Surface but don't raise.
                log.warning(
                    "blog_post_parse_failed_attempt_2",
                    user_id=str(user.id),
                    model=model_id,
                )

        # Render markdown when we have structured output; otherwise the
        # raw model text is already in `outcome.rendered_text`.
        if outcome.result is not None:
            rendered_text = render_blog_post(outcome.result)
            result_jsonb = outcome.result.model_dump()
            wc = word_count(rendered_text)
        else:
            rendered_text = outcome.rendered_text
            result_jsonb = None
            wc = word_count(rendered_text)

        piece = ContentPiece(
            user_id=user.id,
            content_type=ContentType.BLOG_POST,
            topic=request.topic,
            tone=request.tone,
            target_audience=request.target_audience,
            brand_voice_id=request.brand_voice_id,
            prompt_version=BLOG_POST_PROMPT_VERSION,
            system_prompt_snapshot=system_prompt,
            user_prompt_snapshot=user_prompt,
            result=result_jsonb,
            rendered_text=rendered_text,
            result_parse_status=outcome.status,
            word_count=wc,
            model_id=model_id,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
        )
        return await self._repo.create(piece)

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _try_parse(raw: str, success_status: ResultParseStatus) -> _ParseOutcome:
        """Parse raw text as JSON and validate against `BlogPostResult`.

        On any failure return an outcome with `result=None` and the raw
        text preserved — the caller decides whether to retry or degrade.
        """
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return _ParseOutcome(
                result=None,
                rendered_text=raw,
                status=ResultParseStatus.FAILED,
            )
        try:
            parsed = BlogPostResult.model_validate(payload)
        except PydanticValidationError:
            return _ParseOutcome(
                result=None,
                rendered_text=raw,
                status=ResultParseStatus.FAILED,
            )
        return _ParseOutcome(
            result=parsed,
            rendered_text="",  # caller renders from `result`
            status=success_status,
        )

    async def _call_corrective_retry(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        previous_raw: str,
    ) -> LLMResult:
        """Second-pass call that re-emphasizes valid JSON.

        We feed the prior raw response back into the user prompt so the
        model can see what it sent and correct course. `json_schema` is
        intentionally NOT passed: stage-2 is a free-form retry whose
        instructions live in plain text. If the model could not produce
        schema-conforming JSON under strict mode, asking again under
        strict mode tends to fail the same way.
        """
        retry_user_prompt = (
            f"{user_prompt}\n\n"
            f"Previous response (invalid):\n{previous_raw}\n\n"
            f"{CORRECTIVE_RETRY_INSTRUCTION}"
        )
        return await self._provider.generate(
            system_prompt=system_prompt,
            user_prompt=retry_user_prompt,
            json_schema=None,
            content_type=ContentType.BLOG_POST.value,
        )
