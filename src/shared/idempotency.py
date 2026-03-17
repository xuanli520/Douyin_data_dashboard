import binascii
import json
import os
from typing import Any

from src.cache import resolve_sync_redis_client


class FunboostIdempotencyHelper:
    def __init__(self, redis_client: Any | None, task_name: str):
        self.redis = resolve_sync_redis_client(redis_client)
        self.task_name = task_name

    def _lock_key(self, key: str) -> str:
        return f"douyin:lock:{self.task_name}:{key}"

    def _result_key(self, key: str) -> str:
        return f"douyin:result:{self.task_name}:{key}"

    def acquire_lock(self, key: str, ttl: int) -> str | None:
        token = binascii.hexlify(os.urandom(16)).decode()
        acquired = self.redis.set(self._lock_key(key), token, ex=ttl, nx=True)
        return token if acquired else None

    def refresh_lock(self, key: str, token: str, new_ttl: int) -> bool:
        lock_key = self._lock_key(key)
        result = self.redis.eval(
            """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('expire', KEYS[1], ARGV[2])
            else
                return 0
            end
            """,
            1,
            lock_key,
            token,
            new_ttl,
        )
        return bool(result)

    def release_lock(self, key: str, token: str) -> None:
        self.redis.eval(
            """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
            """,
            1,
            self._lock_key(key),
            token,
        )

    def cache_result(self, key: str, result: dict, ttl: int = 86400) -> None:
        self.redis.set(self._result_key(key), json.dumps(result), ex=ttl)

    def get_cached_result(self, key: str) -> dict | None:
        cached = self.redis.get(self._result_key(key))
        if cached is None:
            return None
        if isinstance(cached, bytes):
            cached = cached.decode()
        return json.loads(cached)
