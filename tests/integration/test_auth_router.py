"""Test custom authentication routes."""

from httpx import ASGITransport, AsyncClient

from src.auth.captcha import get_captcha_service
from src.cache import get_cache
from src.main import app
from src.shared.errors import ErrorCode


def _find_set_cookie(response, cookie_name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{cookie_name}="):
            return header
    return None


def _cookie_value(set_cookie: str) -> str:
    return set_cookie.split(";", maxsplit=1)[0].split("=", maxsplit=1)[1]


class _MockCaptchaService:
    async def verify(self, captcha_verify_param: str) -> bool:
        return bool(captcha_verify_param)


async def test_login_success_sets_cookies(test_client, test_user, settings):
    response = await test_client.post(
        "/api/v1/auth/login",
        data={
            "username": "test@example.com",
            "password": "testpassword123",
            "captchaVerifyParam": "valid",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" not in data
    assert "token_type" not in data
    assert "refresh_token" not in data

    access_cookie = _find_set_cookie(response, settings.auth.access_cookie_name)
    refresh_cookie = _find_set_cookie(response, settings.auth.refresh_cookie_name)
    assert access_cookie is not None
    assert refresh_cookie is not None

    assert "HttpOnly" in access_cookie
    assert "HttpOnly" in refresh_cookie
    assert "Path=/" in access_cookie
    assert "Path=/" in refresh_cookie
    assert "SameSite=lax" in access_cookie
    assert "SameSite=lax" in refresh_cookie
    assert "Domain=" not in access_cookie
    assert "Domain=" not in refresh_cookie
    assert "Secure" not in access_cookie
    assert "Secure" not in refresh_cookie


async def test_login_sets_secure_cookie_when_https(
    test_db, local_cache, test_user, settings
):
    async def override_get_cache():
        yield local_cache

    app.dependency_overrides[get_cache] = override_get_cache
    app.dependency_overrides[get_captcha_service] = lambda: _MockCaptchaService()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as client:
            response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": "test@example.com",
                    "password": "testpassword123",
                    "captchaVerifyParam": "valid",
                },
            )
    finally:
        app.dependency_overrides.pop(get_cache, None)
        app.dependency_overrides.pop(get_captcha_service, None)

    assert response.status_code == 200
    access_cookie = _find_set_cookie(response, settings.auth.access_cookie_name)
    refresh_cookie = _find_set_cookie(response, settings.auth.refresh_cookie_name)
    assert access_cookie is not None
    assert refresh_cookie is not None
    assert "Secure" in access_cookie
    assert "Secure" in refresh_cookie


async def test_login_invalid_credentials(test_client, test_user):
    response = await test_client.post(
        "/api/v1/auth/login",
        data={
            "username": "test@example.com",
            "password": "wrongpassword",
            "captchaVerifyParam": "valid",
        },
    )

    assert response.status_code == 401
    data = response.json()
    assert data["msg"] == "Invalid credentials"
    assert data["code"] == ErrorCode.AUTH_INVALID_CREDENTIALS


async def test_login_nonexistent_user(test_client):
    response = await test_client.post(
        "/api/v1/auth/login",
        data={"username": "nonexistent@example.com", "password": "password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.AUTH_INVALID_CREDENTIALS


async def test_users_me_supports_cookie_session(test_client, test_user):
    await test_client.post(
        "/api/v1/auth/login",
        data={
            "username": "test@example.com",
            "password": "testpassword123",
            "captchaVerifyParam": "valid",
        },
    )

    response = await test_client.get("/api/v1/auth/users/me")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == "test@example.com"


async def test_refresh_token_success_by_cookie(test_client, test_user, settings):
    login_response = await test_client.post(
        "/api/v1/auth/login",
        data={
            "username": "test@example.com",
            "password": "testpassword123",
            "captchaVerifyParam": "valid",
        },
    )
    old_access_cookie = _find_set_cookie(
        login_response, settings.auth.access_cookie_name
    )
    assert old_access_cookie is not None

    response = await test_client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    data = response.json()
    assert "access_token" not in data
    assert "token_type" not in data

    access_cookie = _find_set_cookie(response, settings.auth.access_cookie_name)
    assert access_cookie is not None
    assert "HttpOnly" in access_cookie
    assert "SameSite=lax" in access_cookie
    assert "Path=/" in access_cookie
    assert "Domain=" not in access_cookie


async def test_refresh_token_invalid_clears_cookies(test_client, settings):
    test_client.cookies.set(settings.auth.refresh_cookie_name, "invalid_token")

    response = await test_client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.AUTH_TOKEN_INVALID
    access_cookie = _find_set_cookie(response, settings.auth.access_cookie_name)
    refresh_cookie = _find_set_cookie(response, settings.auth.refresh_cookie_name)
    assert access_cookie is not None
    assert refresh_cookie is not None
    assert "Max-Age=0" in access_cookie
    assert "Max-Age=0" in refresh_cookie


async def test_logout_success_revokes_refresh_cookie(test_client, test_user, settings):
    login_response = await test_client.post(
        "/api/v1/auth/login",
        data={
            "username": "test@example.com",
            "password": "testpassword123",
            "captchaVerifyParam": "valid",
        },
    )
    refresh_cookie = _find_set_cookie(login_response, settings.auth.refresh_cookie_name)
    assert refresh_cookie is not None
    refresh_token = _cookie_value(refresh_cookie)

    response = await test_client.post("/api/v1/auth/logout")

    assert response.status_code == 200
    data = response.json()
    assert data["detail"] == "Successfully logged out"
    access_clear = _find_set_cookie(response, settings.auth.access_cookie_name)
    refresh_clear = _find_set_cookie(response, settings.auth.refresh_cookie_name)
    assert access_clear is not None
    assert refresh_clear is not None
    assert "Max-Age=0" in access_clear
    assert "Max-Age=0" in refresh_clear

    test_client.cookies.set(settings.auth.refresh_cookie_name, refresh_token)
    refresh_response = await test_client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 401
    assert refresh_response.json()["code"] == ErrorCode.AUTH_TOKEN_INVALID


async def test_refresh_token_inactive_user(test_client, test_user, test_db):
    from src.auth.models import User

    await test_client.post(
        "/api/v1/auth/login",
        data={
            "username": "test@example.com",
            "password": "testpassword123",
            "captchaVerifyParam": "valid",
        },
    )

    async with test_db() as session:
        user = await session.get(User, test_user.id)
        user.is_active = False
        session.add(user)
        await session.commit()

    response = await test_client.post("/api/v1/auth/refresh")

    assert response.status_code == 403
    data = response.json()
    assert data["msg"] == "User inactive"
    assert data["code"] == ErrorCode.USER_INACTIVE


async def test_reset_password_revokes_tokens(
    test_client, test_user, local_cache, settings
):
    from src.auth.backend import RefreshTokenManager
    from src.config import get_settings

    runtime_settings = get_settings()
    login_response = await test_client.post(
        "/api/v1/auth/login",
        data={
            "username": "test@example.com",
            "password": "testpassword123",
            "captchaVerifyParam": "valid",
        },
    )
    refresh_cookie = _find_set_cookie(login_response, settings.auth.refresh_cookie_name)
    assert refresh_cookie is not None
    refresh_token = _cookie_value(refresh_cookie)

    refresh_manager = RefreshTokenManager(local_cache, runtime_settings)
    await refresh_manager.revoke_all_user_tokens(test_user.id)
    test_client.cookies.set(settings.auth.refresh_cookie_name, refresh_token)

    response = await test_client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.AUTH_TOKEN_INVALID
