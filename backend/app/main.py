"""FastAPI application factory + ASGI entry point.

Starlette stacks middleware in REVERSE order of `add_middleware()` calls:
the last one added is the outermost. So a request flows from the outermost
(last added) wrapper inward, then back outward on the response. The wiring
below reads outer-to-inner along the request path:

  1. CORS (last added, outermost) — preflights short-circuit before any
     other middleware allocates work.
  2. RequestID                    — binds `X-Request-ID` into the contextvar.
  3. AccessLog (first added, innermost) — reads the bound request_id from
     the contextvar so every log line carries it.
  4. Exception handlers           — consistent {error, meta} envelope on
                                    every failure path; runs inside the
                                    middleware stack.
  5. v1 router                    — mounted at /api/v1.
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
from app.db.session import close_db_engine
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
    await close_db_engine()


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

    # Add middleware INNER-MOST first so the LAST-added one wraps outside
    # everything else (Starlette's documented ordering).
    app.add_middleware(AccessLogMiddleware)  # innermost — runs last on the way out
    app.add_middleware(RequestIDMiddleware)  # binds contextvar before AccessLog reads it
    app.add_middleware(
        CORSMiddleware,  # outermost — preflights short-circuit before anything else
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

    register_exception_handlers(app)

    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
