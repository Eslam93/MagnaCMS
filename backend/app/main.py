"""FastAPI application factory + ASGI entry point.

Wiring order is deliberate:
  1. CORS first  — preflights short-circuit before any other middleware runs.
  2. Access log  — logs every completed request with timing + status.
  3. Request ID  — runs *innermost* so the id is bound before any handler
                   work, and unwinds after access logging captures it.
  4. Exception handlers — consistent envelope on every failure path.
  5. v1 router   — mounted at /api/v1.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import v1_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.middleware.logging import AccessLogMiddleware
from app.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("app.startup")
    log.info(
        "application_starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        ai_provider_mode=settings.ai_provider_mode.value,
    )
    yield
    log.info("application_stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI Content Marketing Suite — backend API.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS first so preflights short-circuit.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            REQUEST_ID_HEADER,
            "Idempotency-Key",
        ],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )

    # Starlette stacks middleware in reverse-add order, so AccessLog wraps
    # RequestID — the request_id is bound BEFORE access-log captures the call.
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)

    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
