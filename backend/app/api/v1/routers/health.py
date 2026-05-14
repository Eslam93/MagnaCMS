"""Health endpoint. Reports service version and downstream-dep status.

Real dependency checks attach as the components they depend on land
(DB in P1.2, OpenAI in P1.7, Redis in P11.x). Until then the report is
static and clearly marked `unknown`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import get_settings

router = APIRouter(tags=["system"])


DependencyState = Literal["ok", "unknown", "down"]


class DependencyStatus(BaseModel):
    db: DependencyState = "unknown"
    redis: DependencyState = "unknown"
    openai: DependencyState = "unknown"


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    environment: str
    dependencies: DependencyStatus = Field(default_factory=DependencyStatus)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health and dependency status",
)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        version=settings.app_version,
        environment=settings.environment.value,
    )
