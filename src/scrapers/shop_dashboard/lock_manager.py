from __future__ import annotations

import os
import time
from typing import Any

from redis.exceptions import ResponseError

from src.cache import resolve_sync_redis_client
from src.config import get_settings


class LockManager:
    _RELEASE_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    else
        return 0
    end
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        lock_ttl_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self._lock_ttl_seconds = int(
            lock_ttl_seconds or settings.shop_dashboard.lock_ttl_seconds
        )
        self._redis = resolve_sync_redis_client(redis_client)
        self._memory_locks: dict[str, tuple[str, float]] = {}

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
        set_func = getattr(self._redis, "set", None)
        if not callable(set_func):
            return self._acquire_from_memory(key, token, ttl)
        if set_func(key, token, nx=True, ex=ttl):
            return token
        return None

    def _release(self, key: str, token: str) -> None:
        eval_func = getattr(self._redis, "eval", None)
        if callable(eval_func):
            try:
                eval_func(self._RELEASE_SCRIPT, 1, key, token)
                return
            except ResponseError as exc:
                message = str(exc).lower()
                if "unknown command" not in message or "eval" not in message:
                    raise

        get_func = getattr(self._redis, "get", None)
        delete_func = getattr(self._redis, "delete", None)
        if callable(get_func) and callable(delete_func):
            current = get_func(key)
            if current == token:
                delete_func(key)
            return
        self._release_from_memory(key, token)

    def _acquire_from_memory(
        self, key: str, token: str, ttl_seconds: int
    ) -> str | None:
        now = time.time()
        cached = self._memory_locks.get(key)
        if cached is not None and cached[1] > now:
            return None
        self._memory_locks[key] = (token, now + max(ttl_seconds, 1))
        return token

    def _release_from_memory(self, key: str, token: str) -> None:
        cached = self._memory_locks.get(key)
        if cached is not None and cached[0] == token:
            self._memory_locks.pop(key, None)
