import asyncio
import hashlib
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.auth.backend import RefreshTokenManager
from src.config.auth import AuthSettings
from src.shared.redis_keys import redis_keys


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
