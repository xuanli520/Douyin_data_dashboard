from __future__ import annotations

import os
from typing import Any

from redis import Redis

from src.config import get_settings


class LockManager:
    def __init__(
        self,
        redis_client: Redis | Any | None = None,
        lock_ttl_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self._lock_ttl_seconds = int(
            lock_ttl_seconds or settings.shop_dashboard.lock_ttl_seconds
        )
        self._redis = redis_client or Redis(
            host=settings.cache.host,
            port=settings.cache.port,
            db=settings.cache.db,
            password=settings.cache.password,
            encoding=settings.cache.encoding,
            decode_responses=True,
            socket_timeout=settings.cache.socket_timeout,
            socket_connect_timeout=settings.cache.socket_connect_timeout,
            retry_on_timeout=settings.cache.retry_on_timeout,
        )

    def account_lock_key(self, account_id: str) -> str:
        return f"douyin:account:lock:{account_id}"

    def shop_lock_key(self, shop_id: str) -> str:
        return f"douyin:shop:lock:{shop_id}"

    def acquire_account_lock(
        self, account_id: str, ttl_seconds: int | None = None
    ) -> str | None:
        return self._acquire(self.account_lock_key(account_id), ttl_seconds)

    def release_account_lock(self, account_id: str, token: str) -> None:
        self._release(self.account_lock_key(account_id), token)

    def acquire_shop_lock(
        self, shop_id: str, ttl_seconds: int | None = None
    ) -> str | None:
        return self._acquire(self.shop_lock_key(shop_id), ttl_seconds)

    def release_shop_lock(self, shop_id: str, token: str) -> None:
        self._release(self.shop_lock_key(shop_id), token)

    def _acquire(self, key: str, ttl_seconds: int | None = None) -> str | None:
        token = os.urandom(16).hex()
        ttl = int(ttl_seconds or self._lock_ttl_seconds)
        if self._redis.set(key, token, nx=True, ex=ttl):
            return token
        return None

    def _release(self, key: str, token: str) -> None:
        current = self._redis.get(key)
        if current == token:
            self._redis.delete(key)
