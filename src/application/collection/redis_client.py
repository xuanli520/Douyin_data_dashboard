from __future__ import annotations

import logging
from typing import Any, Protocol, cast

from src.cache import resolve_sync_redis_client
from src.middleware.monitor import observe_shop_dashboard_redis_degraded


class RedisPipeline(Protocol):
    def incr(self, key: str) -> Any: ...

    def expire(self, key: str, ttl: int) -> Any: ...

    def execute(self) -> list[Any]: ...


class RedisClient(Protocol):
    def get(self, key: str) -> Any: ...

    def set(
        self,
        key: str,
        value: Any,
        *,
        ex: int | None = None,
        nx: bool = False,
        **kwargs: Any,
    ) -> Any: ...

    def delete(self, *keys: str) -> Any: ...

    def eval(self, script: str, numkeys: int, *args: Any) -> Any: ...

    def pipeline(self, *, transaction: bool = True) -> RedisPipeline: ...


class RedisClientUnavailableError(RuntimeError):
    pass


class _NullRedisPipeline:
    def __init__(self, *, reason: str) -> None:
        self._reason = reason

    def _raise(self, operation: str) -> None:
        raise RedisClientUnavailableError(
            f"redis unavailable operation={operation} reason={self._reason}"
        )

    def incr(self, key: str) -> Any:
        _ = key
        self._raise("pipeline.incr")

    def expire(self, key: str, ttl: int) -> Any:
        _ = (key, ttl)
        self._raise("pipeline.expire")

    def execute(self) -> list[Any]:
        self._raise("pipeline.execute")


class NullRedisClient:
    def __init__(self, *, reason: str = "unavailable") -> None:
        self._reason = reason

    def _raise(self, operation: str) -> None:
        raise RedisClientUnavailableError(
            f"redis unavailable operation={operation} reason={self._reason}"
        )

    def get(self, key: str) -> Any:
        _ = key
        self._raise("get")

    def set(
        self,
        key: str,
        value: Any,
        *,
        ex: int | None = None,
        nx: bool = False,
        **kwargs: Any,
    ) -> Any:
        _ = (key, value, ex, nx, kwargs)
        self._raise("set")

    def delete(self, *keys: str) -> Any:
        _ = keys
        self._raise("delete")

    def eval(self, script: str, numkeys: int, *args: Any) -> Any:
        _ = (script, numkeys, args)
        self._raise("eval")

    def pipeline(self, *, transaction: bool = True) -> RedisPipeline:
        _ = transaction
        return _NullRedisPipeline(reason=self._reason)


_DEGRADED_REDIS_REPORTED_COMPONENTS: set[str] = set()


def resolve_collection_redis_client(
    redis_client: Any | None,
    *,
    component: str,
    logger: logging.Logger,
) -> RedisClient:
    if isinstance(redis_client, NullRedisClient):
        _report_degraded_redis(component=component, logger=logger, error=None)
        return redis_client
    try:
        resolved = resolve_sync_redis_client(redis_client)
    except Exception as exc:
        _report_degraded_redis(component=component, logger=logger, error=exc)
        return NullRedisClient(reason=str(exc) or exc.__class__.__name__)
    return cast(RedisClient, resolved)


def _report_degraded_redis(
    *,
    component: str,
    logger: logging.Logger,
    error: Exception | None,
) -> None:
    if component in _DEGRADED_REDIS_REPORTED_COMPONENTS:
        return
    _DEGRADED_REDIS_REPORTED_COMPONENTS.add(component)
    observe_shop_dashboard_redis_degraded(component=component)
    if error is None:
        logger.warning(
            "shop dashboard redis degraded to null client component=%s",
            component,
        )
        return
    logger.warning(
        "shop dashboard redis degraded to null client component=%s error=%s",
        component,
        error,
    )
