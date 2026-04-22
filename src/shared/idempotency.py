import binascii
import json
import logging
import os
from typing import Any

from redis.exceptions import RedisError

from src.cache import resolve_sync_redis_client

logger = logging.getLogger(__name__)


class FunboostIdempotencyHelper:
    _REFRESH_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('expire', KEYS[1], ARGV[2])
    else
        return 0
    end
    """
    _RELEASE_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    else
        return 0
    end
    """

    def __init__(self, redis_client: Any | None, task_name: str):
        self.redis = resolve_sync_redis_client(redis_client)
        self.task_name = task_name

    def _lock_key(self, key: str) -> str:
        return f"douyin:lock:{self.task_name}:{key}"

    def _result_key(self, key: str) -> str:
        return f"douyin:result:{self.task_name}:{key}"

    def _run_lock_script(self, script: str, lock_key: str, *args: Any) -> Any:
        try:
            return self.redis.eval(script, 1, lock_key, *args)
        except RedisError:
            register_script = getattr(self.redis, "register_script", None)
            if not callable(register_script):
                raise
            runner = register_script(script)
            return runner(keys=[lock_key], args=list(args), client=self.redis)

    def acquire_lock(self, key: str, ttl: int) -> str | None:
        token = binascii.hexlify(os.urandom(16)).decode()
        acquired = self.redis.set(self._lock_key(key), token, ex=ttl, nx=True)
        return token if acquired else None

    def refresh_lock(self, key: str, token: str, new_ttl: int) -> bool:
        lock_key = self._lock_key(key)
        try:
            result = self._run_lock_script(
                self._REFRESH_SCRIPT,
                lock_key,
                token,
                new_ttl,
            )
        except RedisError:
            return False
        return bool(result)

    def release_lock(self, key: str, token: str) -> None:
        lock_key = self._lock_key(key)
        try:
            self._run_lock_script(
                self._RELEASE_SCRIPT,
                lock_key,
                token,
            )
            return
        except RedisError:
            logger.error(
                "failed to release idempotency lock task_name=%s key=%s",
                self.task_name,
                key,
                exc_info=True,
            )

    def cache_result(self, key: str, result: dict, ttl: int = 86400) -> None:
        try:
            self.redis.set(self._result_key(key), json.dumps(result), ex=ttl)
        except RedisError:
            logger.warning(
                "failed to cache idempotency result task_name=%s key=%s",
                self.task_name,
                key,
                exc_info=True,
            )

    def get_cached_result(self, key: str) -> dict | None:
        cached = self.redis.get(self._result_key(key))
        if cached is None:
            return None
        if isinstance(cached, bytes):
            cached = cached.decode()
        return json.loads(cached)
