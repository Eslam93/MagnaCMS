"""FastAPI application factory + ASGI entry point.

Starlette stacks middleware in REVERSE order of `add_middleware()` calls:
the last one added is the outermost. So a request flows from the outermost
(last added) wrapper inward, then back outward on the response. The wiring
below reads outer-to-inner along the request path:

  1. CORS (last added, outermost) — preflights short-circuit before any
     other middleware allocates work.
  2. SecurityHeaders              — adds nosniff / DENY / CSP / HSTS to
                                    every response on its way out,
                                    INCLUDING 429s emitted by RateLimit.
  3. RequestID                    — binds `X-Request-ID` into the contextvar
                                    before RateLimit reads it for the
                                    429 envelope.
  4. RateLimit                    — rejects 429 before the request reaches
                                    auth code; bound IP is the real TCP
                                    peer (forwarded-for is unsafe as
                                    rate-limit identity until P11.x).
                                    Position INSIDE SecurityHeaders +
                                    RequestID so 429 responses carry both.
  5. AccessLog (first added, innermost) — reads the bound request_id from
     the contextvar so every log line carries it.
  6. Exception handlers           — consistent {error, meta} envelope on
                                    every failure path; runs inside the
                                    middleware stack.
  7. v1 router                    — mounted at /api/v1.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import v1_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import close_db_engine
from app.middleware.logging import AccessLogMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

# Per-path requests-per-minute caps. /auth/login + /auth/register are
# the brief's explicit targets; /auth/refresh is added because the
# security-review pass on P1.6 flagged the unauthenticated endpoint as
# a token-space probing surface. P11.3 will swap this for a Redis-
# backed sliding window with per-account dimensions.
_AUTH_RATE_LIMITS: Final[dict[str, int]] = {
    "/api/v1/auth/login": 10,
    "/api/v1/auth/register": 10,
    "/api/v1/auth/refresh": 10,
}


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
    app.add_middleware(RateLimitMiddleware, rules=_AUTH_RATE_LIMITS)
    app.add_middleware(
        RequestIDMiddleware
    )  # binds contextvar so RateLimit's 429 envelope carries it
    app.add_middleware(SecurityHeadersMiddleware)  # wraps RateLimit so 429 carries security headers
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
