import asyncio
import hashlib
from datetime import datetime, timezone

import pytest
from fastapi import Request
from fastapi.responses import Response
from pydantic import ValidationError

from src.api.oauth import create_oauth_router
from src.auth.backend import (
    RefreshTokenManager,
    bearer_auth_backend,
    bearer_transport,
    cookie_auth_backend,
    cookie_transport,
)
from src.auth.cookies import bind_auth_request_context, set_auth_cookie
from src.config import get_settings
from src.config.auth import AuthSettings
from src.shared.redis_keys import redis_keys


def _build_request(
    *,
    scheme: str = "http",
    headers: list[tuple[bytes, bytes]] | None = None,
    cookies: dict[str, str] | None = None,
) -> Request:
    request_headers = list(headers or [])
    if cookies:
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        request_headers.append((b"cookie", cookie_header.encode()))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": scheme,
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": request_headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
        }
    )


async def test_create_refresh_token(local_cache, settings):
    manager = RefreshTokenManager(local_cache, settings)
    token = await manager.create_refresh_token(1, "Mozilla/5.0")

    assert token is not None
    assert len(token) > 0


async def test_verify_refresh_token(local_cache, settings):
    manager = RefreshTokenManager(local_cache, settings)
    token = await manager.create_refresh_token(1, "Mozilla/5.0")

    user_id = await manager.verify_refresh_token(token)
    assert user_id == 1


async def test_verify_invalid_token(local_cache, settings):
    manager = RefreshTokenManager(local_cache, settings)

    user_id = await manager.verify_refresh_token("invalid_token")
    assert user_id is None


def test_auth_settings_reject_unsupported_jwt_algorithm():
    with pytest.raises(ValidationError):
        AuthSettings(jwt_secret="secret", jwt_algorithm="RS256")


@pytest.mark.parametrize("cached_value", ["not-an-int", "1:ua"])
async def test_verify_refresh_token_with_malformed_cache_value_returns_none(
    local_cache, settings, cached_value
):
    manager = RefreshTokenManager(local_cache, settings)
    token = await manager.create_refresh_token(1, "Mozilla/5.0")
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    await local_cache.set(
        redis_keys.refresh_token(token_hash=token_hash),
        cached_value,
        ttl=settings.auth.refresh_token_lifetime_seconds,
    )

    assert await manager.verify_refresh_token(token) is None


async def test_revoke_token(local_cache, settings):
    manager = RefreshTokenManager(local_cache, settings)
    token = await manager.create_refresh_token(1, "Mozilla/5.0")

    await manager.revoke_token(token)

    user_id = await manager.verify_refresh_token(token)
    assert user_id is None


async def test_revoke_all_user_tokens(local_cache, settings):
    manager = RefreshTokenManager(local_cache, settings)
    token1 = await manager.create_refresh_token(1, "Mozilla/5.0")
    token2 = await manager.create_refresh_token(1, "Chrome/98.0")

    await manager.revoke_all_user_tokens(1)

    assert await manager.verify_refresh_token(token1) is None
    assert await manager.verify_refresh_token(token2) is None


async def test_revoke_all_user_tokens_revokes_equal_timestamp_token(
    local_cache, settings
):
    manager = RefreshTokenManager(local_cache, settings)
    token = await manager.create_refresh_token(1, "Mozilla/5.0")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    token_key = redis_keys.refresh_token(token_hash=token_hash)
    token_payload = await local_cache.get(token_key)
    assert token_payload is not None
    token_created_time = token_payload.split(":", maxsplit=2)[2]

    await local_cache.set(
        redis_keys.user_revoked(user_id=1),
        token_created_time,
        ttl=settings.auth.refresh_token_lifetime_seconds,
    )

    assert await manager.verify_refresh_token(token) is None


async def test_revoke_all_user_tokens_revokes_tokens_with_same_timestamp(
    local_cache, settings, monkeypatch
):
    manager = RefreshTokenManager(local_cache, settings)

    fixed_time = datetime(2026, 3, 6, 12, 0, 0, tzinfo=timezone.utc)

    class _FrozenDateTime:
        @staticmethod
        def now(tz=None):
            return fixed_time

        @staticmethod
        def fromisoformat(value: str):
            return datetime.fromisoformat(value)

    monkeypatch.setattr("src.auth.backend.datetime", _FrozenDateTime)

    token = await manager.create_refresh_token(1, "Mozilla/5.0")
    await manager.revoke_all_user_tokens(1)

    assert await manager.verify_refresh_token(token) is None


async def test_revoke_all_user_tokens_preserves_new_tokens(local_cache, settings):
    manager = RefreshTokenManager(local_cache, settings)
    old_token = await manager.create_refresh_token(1, "Mozilla/5.0")

    await asyncio.sleep(0.01)
    await manager.revoke_all_user_tokens(1)
    await asyncio.sleep(0.01)

    new_token = await manager.create_refresh_token(1, "Chrome/98.0")

    assert await manager.verify_refresh_token(old_token) is None
    assert await manager.verify_refresh_token(new_token) == 1


async def test_token_with_no_device_info(local_cache, settings):
    manager = RefreshTokenManager(local_cache, settings)
    token = await manager.create_refresh_token(1)

    user_id = await manager.verify_refresh_token(token)
    assert user_id == 1


def test_cookie_transport_settings(settings):
    assert cookie_transport.cookie_name == settings.auth.access_cookie_name
    assert cookie_transport.cookie_path == settings.auth.cookie_path
    assert cookie_transport.cookie_samesite == settings.auth.cookie_samesite
    assert cookie_transport.cookie_secure == settings.auth.cookie_secure
    assert cookie_transport.cookie_domain is None
    assert cookie_transport.cookie_httponly is True


def test_auth_backends_keep_cookie_and_bearer():
    assert cookie_auth_backend.name == "cookie"
    assert bearer_auth_backend.name == "jwt"
    assert bearer_transport.scheme.model.flows.password.tokenUrl == "/auth/login"


def test_set_auth_cookie_honors_cookie_secure_config(monkeypatch):
    monkeypatch.setenv("AUTH__COOKIE_SECURE", "true")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        response = Response()

        set_auth_cookie(
            response,
            name=settings.auth.access_cookie_name,
            value="token",
            max_age=60,
            request=_build_request(),
            settings=settings,
        )

        assert "Secure" in response.headers["set-cookie"]
    finally:
        get_settings.cache_clear()


async def test_cookie_transport_uses_runtime_settings_and_request_context(monkeypatch):
    monkeypatch.setenv("AUTH__ACCESS_COOKIE_NAME", "session_access")
    monkeypatch.setenv("AUTH__COOKIE_PATH", "/api/v1")
    monkeypatch.setenv("AUTH__COOKIE_SECURE", "false")
    get_settings.cache_clear()

    bind = bind_auth_request_context(
        _build_request(headers=[(b"x-forwarded-proto", b"https")])
    )
    await anext(bind)

    try:
        response = await cookie_transport.get_login_response("token")
        set_cookie = response.headers["set-cookie"]
        assert set_cookie.startswith("session_access=token;")
        assert "Path=/api/v1" in set_cookie
        assert "Secure" in set_cookie

        token = await cookie_transport.scheme(
            _build_request(cookies={"session_access": "token"})
        )
        assert token == "token"
    finally:
        with pytest.raises(StopAsyncIteration):
            await anext(bind)
        get_settings.cache_clear()


def test_create_oauth_router_binds_auth_request_context(monkeypatch):
    monkeypatch.setenv("AUTH__OAUTH_GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("AUTH__OAUTH_GOOGLE_CLIENT_SECRET", "google-secret")
    get_settings.cache_clear()

    try:
        router = create_oauth_router(get_settings())
        assert router.dependencies[0].dependency is bind_auth_request_context
    finally:
        get_settings.cache_clear()
