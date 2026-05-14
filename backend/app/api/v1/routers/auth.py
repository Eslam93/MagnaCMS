"""/auth/* endpoints — register, login, current user.

Refresh + logout endpoints arrive in P1.6. This module wires the refresh
cookie shape so P1.6 can read it without further fuss.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.v1.deps import CurrentUser
from app.core.config import Environment, get_settings
from app.db.session import DbSession
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.auth_service import AuthService, AuthTokens

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"


def _set_refresh_cookie(response: Response, tokens: AuthTokens) -> None:
    """Set the httpOnly refresh cookie. Secure flag follows the environment."""
    settings = get_settings()
    secure = settings.environment in {Environment.PROD, Environment.STAGING}
    max_age = int((tokens.refresh_expires_at.timestamp()) - 0)  # absolute expiry
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        tokens.refresh_token_raw,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.jwt_refresh_token_ttl_seconds,
        path="/api/v1/auth",
    )
    # `max_age` is what we want clients to honor; `expires` would override.
    _ = max_age  # kept for future audit if we switch to absolute expires


def _client_user_agent(request: Request) -> str | None:
    ua = request.headers.get("user-agent")
    return ua[:500] if ua else None


def _client_ip(request: Request) -> str | None:
    # Behind App Runner / Amplify there's usually a forwarded-for chain. For now
    # take the first hop; production proxy config arrives with the deploy.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    return request.client.host if request.client else None


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> AuthResponse:
    user, tokens = await AuthService(db).register(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        user_agent=_client_user_agent(request),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, tokens)
    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Authenticate and receive a new token pair",
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> AuthResponse:
    user, tokens = await AuthService(db).login(
        email=body.email,
        password=body.password,
        user_agent=_client_user_agent(request),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, tokens)
    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the authenticated user",
)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
