"""Integration tests for /auth/register, /auth/login, /auth/me.

Each test runs inside a transaction that rolls back on teardown, so the
database stays clean and tests are order-independent.
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_register_creates_user_and_issues_tokens(
    integration_client: AsyncClient,
) -> None:
    response = await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "Secret123",
            "full_name": "Alice Example",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["full_name"] == "Alice Example"
    assert "id" in body["user"]
    assert body["access_token"]
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] > 0
    # Refresh token rides in a cookie, not the body.
    assert "refresh_token" not in body
    assert response.cookies.get("refresh_token")


async def test_register_rejects_duplicate_email(
    integration_client: AsyncClient,
) -> None:
    body = {
        "email": "dup@example.com",
        "password": "Secret123",
        "full_name": "First",
    }
    first = await integration_client.post("/api/v1/auth/register", json=body)
    assert first.status_code == 201

    body2 = {**body, "password": "Another456", "full_name": "Second"}
    second = await integration_client.post("/api/v1/auth/register", json=body2)
    assert second.status_code == 409
    payload = second.json()
    assert payload["error"]["code"] == "EMAIL_TAKEN"
    assert payload["error"]["details"]["field"] == "email"


async def test_register_rejects_weak_password(
    integration_client: AsyncClient,
) -> None:
    response = await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "12345678",  # passes Pydantic min_length, fails our checks
            "full_name": "Weak",
        },
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "WEAK_PASSWORD"


async def test_login_with_correct_credentials_succeeds(
    integration_client: AsyncClient,
) -> None:
    await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "bob@example.com",
            "password": "Secret123",
            "full_name": "Bob",
        },
    )
    response = await integration_client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "Secret123"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["email"] == "bob@example.com"
    assert body["access_token"]
    assert response.cookies.get("refresh_token")


async def test_login_with_wrong_password_returns_401(
    integration_client: AsyncClient,
) -> None:
    await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "carol@example.com",
            "password": "Secret123",
            "full_name": "Carol",
        },
    )
    response = await integration_client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "WrongPassword1"},
    )
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_with_unknown_email_returns_same_401(
    integration_client: AsyncClient,
) -> None:
    """Unknown email must produce the same error as wrong password — never
    leak which one to the caller."""
    response = await integration_client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "Secret123"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_with_valid_token_returns_user(
    integration_client: AsyncClient,
) -> None:
    reg = await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "dave@example.com",
            "password": "Secret123",
            "full_name": "Dave",
        },
    )
    token = reg.json()["access_token"]
    response = await integration_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "dave@example.com"


async def test_me_without_token_returns_401(
    integration_client: AsyncClient,
) -> None:
    response = await integration_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MISSING_TOKEN"


async def test_me_with_invalid_token_returns_401(
    integration_client: AsyncClient,
) -> None:
    response = await integration_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"
