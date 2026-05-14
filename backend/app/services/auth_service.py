"""Auth business logic: register, login, current user.

Refresh-token rotation + logout arrive in P1.6 (the conditional-update
atomicity story is its own thing). For now we issue a fresh refresh
token on login and persist its hash; the consumer of that token lands
next.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, UnauthorizedError, ValidationError
from app.core.security import (
    PasswordTooWeakError,
    create_access_token,
    generate_refresh_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.db.models import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository


@dataclass(frozen=True)
class AuthTokens:
    """The pair issued on login / register.

    `access_token` goes in the response body; `refresh_token_raw` is the
    value the route sets into an httpOnly cookie.
    """

    access_token: str
    access_expires_in: int
    refresh_token_raw: str
    refresh_expires_at: datetime


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._refresh_tokens = RefreshTokenRepository(session)

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, AuthTokens]:
        try:
            validate_password_strength(password)
        except PasswordTooWeakError as exc:
            raise ValidationError(str(exc), code="WEAK_PASSWORD") from exc

        try:
            user = await self._users.create(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
            )
        except IntegrityError as exc:
            # The unique constraint on users.email — case-insensitive via CITEXT.
            await self._session.rollback()
            raise ConflictError(
                "Email is already registered.",
                code="EMAIL_TAKEN",
                details={"field": "email"},
            ) from exc

        tokens = await self._mint_tokens(user, user_agent=user_agent, ip_address=ip_address)
        return user, tokens

    async def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, AuthTokens]:
        user = await self._users.find_by_email(email)
        # Same error for "no such user" and "wrong password" — never leak
        # which one to a caller. The cost of a wasted bcrypt verify when the
        # user doesn't exist is the price of timing-equivalence.
        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password.", code="INVALID_CREDENTIALS")
        await self._users.touch_last_login(user)
        tokens = await self._mint_tokens(user, user_agent=user_agent, ip_address=ip_address)
        return user, tokens

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self._users.find_by_id(user_id)
        if user is None:
            raise UnauthorizedError("Authenticated user no longer exists.")
        return user

    async def _mint_tokens(
        self,
        user: User,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthTokens:
        settings = get_settings()
        access_token = create_access_token(subject=str(user.id))
        raw_refresh, hashed_refresh = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_token_ttl_seconds)
        await self._refresh_tokens.create(
            user_id=user.id,
            token_hash=hashed_refresh,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return AuthTokens(
            access_token=access_token,
            access_expires_in=settings.jwt_access_token_ttl_seconds,
            refresh_token_raw=raw_refresh,
            refresh_expires_at=expires_at,
        )
