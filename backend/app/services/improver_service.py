"""Improver service — analyze + rewrite, two-pass chain.

PROJECT_BRIEF §7.6 asks for a two-call chain: ANALYZE returns issues +
planned changes, REWRITE consumes those changes and returns the final
improved text + explanation + structured summary. This module wires
the chain to the same three-stage parse fallback the content service
uses, applied independently to each stage.

Stage breakdown:

  ANALYZE
    1. strict json_schema → ok, return planned_changes
    2. corrective retry without json_schema
    3. degraded — return an empty planned_changes list (the rewriter
       still runs; the goal hint alone drives it)

  REWRITE
    1. strict json_schema → ok, return ImprovementResult
    2. corrective retry without json_schema
    3. degraded — `improved_text` falls back to the model's raw output;
       `explanation` defaults to a single "Rewrite returned in fallback
       mode" line; `changes_summary` defaults to zero deltas. The
       persisted row is still useful — the user sees something — and
       Sentry logs the drift.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Improvement, User
from app.prompts import improver as improver_prompt
from app.providers.llm.base import ILLMProvider
from app.repositories.improvement_repository import ImprovementRepository
from app.schemas.improvement import (
    ImprovementChangesSummary,
    ImprovementResult,
    ImproveRequest,
)

log = get_logger(__name__)


# ── intermediate types ─────────────────────────────────────────────────


@dataclass(frozen=True)
class _AnalyzeOutcome:
    planned_changes: list[str]
    issues: list[str]
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


@dataclass(frozen=True)
class _RewriteOutcome:
    result: ImprovementResult
    degraded: bool
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


# ── service ────────────────────────────────────────────────────────────


def _word_count(text_value: str) -> int:
    return len(text_value.split()) if text_value.strip() else 0


class ImproverService:
    """Run the analyze + rewrite chain and persist the result."""

    def __init__(self, session: AsyncSession, provider: ILLMProvider) -> None:
        self._session = session
        self._provider = provider
        self._repo = ImprovementRepository(session)

    async def improve(
        self,
        *,
        user: User,
        request: ImproveRequest,
    ) -> Improvement:
        analyze = await self._run_analyze(request)
        rewrite = await self._run_rewrite(request, analyze.planned_changes)

        improvement = Improvement(
            user_id=user.id,
            original_text=request.original_text,
            improved_text=rewrite.result.improved_text,
            goal=request.goal,
            new_audience=request.new_audience,
            explanation=rewrite.result.explanation,
            changes_summary=rewrite.result.changes_summary.model_dump(),
            original_word_count=_word_count(request.original_text),
            improved_word_count=_word_count(rewrite.result.improved_text),
            model_id=rewrite.model,
            input_tokens=analyze.input_tokens + rewrite.input_tokens,
            output_tokens=analyze.output_tokens + rewrite.output_tokens,
            cost_usd=analyze.cost_usd + rewrite.cost_usd,
        )
        return await self._repo.create(improvement)

    # ── analyze ────────────────────────────────────────────────────────

    async def _run_analyze(self, request: ImproveRequest) -> _AnalyzeOutcome:
        system_prompt, user_prompt = improver_prompt.build_analyze(
            original_text=request.original_text,
            goal=request.goal,
            new_audience=request.new_audience,
        )

        attempt1 = await self._provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=improver_prompt.ANALYZE_JSON_SCHEMA["schema"],
            content_type="improver_analysis",
        )
        parsed = _parse_analyze(attempt1.raw_text)
        total_in = attempt1.input_tokens
        total_out = attempt1.output_tokens
        total_cost = Decimal(str(attempt1.cost_usd))

        if parsed is None:
            log.warning("improver_analyze_parse_failed_attempt_1", model=attempt1.model)
            retry_prompt = (
                f"{user_prompt}\n\n"
                f"Previous response (invalid):\n{attempt1.raw_text}\n\n"
                f"{improver_prompt.CORRECTIVE_RETRY_INSTRUCTION_ANALYZE}"
            )
            attempt2 = await self._provider.generate(
                system_prompt=system_prompt,
                user_prompt=retry_prompt,
                json_schema=None,
                content_type="improver_analysis",
            )
            parsed = _parse_analyze(attempt2.raw_text)
            total_in += attempt2.input_tokens
            total_out += attempt2.output_tokens
            total_cost += Decimal(str(attempt2.cost_usd))

            if parsed is None:
                log.warning("improver_analyze_parse_failed_attempt_2", model=attempt2.model)

        planned: list[str] = parsed["planned_changes"] if parsed else []
        issues: list[str] = parsed["issues"] if parsed else []
        return _AnalyzeOutcome(
            planned_changes=planned,
            issues=issues,
            model=attempt1.model,
            input_tokens=total_in,
            output_tokens=total_out,
            cost_usd=total_cost,
        )

    # ── rewrite ────────────────────────────────────────────────────────

    async def _run_rewrite(
        self,
        request: ImproveRequest,
        planned_changes: list[str],
    ) -> _RewriteOutcome:
        system_prompt, user_prompt = improver_prompt.build_rewrite(
            original_text=request.original_text,
            goal=request.goal,
            planned_changes=planned_changes,
            new_audience=request.new_audience,
        )

        attempt1 = await self._provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=improver_prompt.REWRITE_JSON_SCHEMA["schema"],
            content_type="improver_rewrite",
        )
        parsed = _parse_rewrite(attempt1.raw_text)
        total_in = attempt1.input_tokens
        total_out = attempt1.output_tokens
        total_cost = Decimal(str(attempt1.cost_usd))
        raw_for_fallback = attempt1.raw_text

        if parsed is None:
            log.warning("improver_rewrite_parse_failed_attempt_1", model=attempt1.model)
            retry_prompt = (
                f"{user_prompt}\n\n"
                f"Previous response (invalid):\n{attempt1.raw_text}\n\n"
                f"{improver_prompt.CORRECTIVE_RETRY_INSTRUCTION_REWRITE}"
            )
            attempt2 = await self._provider.generate(
                system_prompt=system_prompt,
                user_prompt=retry_prompt,
                json_schema=None,
                content_type="improver_rewrite",
            )
            parsed = _parse_rewrite(attempt2.raw_text)
            total_in += attempt2.input_tokens
            total_out += attempt2.output_tokens
            total_cost += Decimal(str(attempt2.cost_usd))
            raw_for_fallback = attempt2.raw_text

            if parsed is None:
                log.warning("improver_rewrite_parse_failed_attempt_2", model=attempt2.model)
                parsed = ImprovementResult(
                    improved_text=raw_for_fallback or request.original_text,
                    explanation=[
                        "Rewrite returned in fallback mode — formatting may be inconsistent."
                    ],
                    changes_summary=ImprovementChangesSummary(
                        tone_shift="unchanged",
                        length_change_pct=0.0,
                        key_additions=[],
                        key_removals=[],
                    ),
                )
                return _RewriteOutcome(
                    result=parsed,
                    degraded=True,
                    model=attempt1.model,
                    input_tokens=total_in,
                    output_tokens=total_out,
                    cost_usd=total_cost,
                )

        return _RewriteOutcome(
            result=parsed,
            degraded=False,
            model=attempt1.model,
            input_tokens=total_in,
            output_tokens=total_out,
            cost_usd=total_cost,
        )


# ── parsers ────────────────────────────────────────────────────────────


def _parse_analyze(raw: str) -> dict[str, list[str]] | None:
    """Parse an analyze response. Returns dict on success; None on failure."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    issues = payload.get("issues")
    changes = payload.get("planned_changes")
    if not isinstance(issues, list) or not isinstance(changes, list):
        return None
    issues = [str(x) for x in issues]
    changes = [str(x) for x in changes]
    return {"issues": issues, "planned_changes": changes}


def _parse_rewrite(raw: str) -> ImprovementResult | None:
    """Parse a rewrite response. Returns ImprovementResult on success;
    None on JSON or schema failure."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    try:
        return ImprovementResult.model_validate(payload)
    except PydanticValidationError:
        return None
