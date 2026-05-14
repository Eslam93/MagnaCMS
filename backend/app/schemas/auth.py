"""Pydantic request / response schemas for the /auth/* endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    """Public user representation. Never includes password material."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    email_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class AuthResponse(BaseModel):
    """Returned by /auth/register and /auth/login.

    The refresh token rides in an httpOnly cookie on the same response —
    it is intentionally NOT in this body.
    """

    user: UserResponse
    access_token: str
    token_type: str = "Bearer"  # noqa: S105  # OAuth2 token-type literal, not a secret
    expires_in: int  # seconds until access_token expires
