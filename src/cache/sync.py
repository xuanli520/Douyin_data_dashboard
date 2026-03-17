from __future__ import annotations

from typing import Any

from redis import Redis

from src.config import get_settings


class SyncRedisCache:
    def __init__(
        self,
        *,
        client: Any | None = None,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        encoding: str = "utf-8",
        decode_responses: bool = True,
        socket_timeout: int = 5,
        socket_connect_timeout: int = 5,
    ) -> None:
        if client is not None:
            self._client = client
            return
        self._client = Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            encoding=encoding,
            decode_responses=decode_responses,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
        )

    @classmethod
    def from_settings(cls, *, db: int | None = None) -> SyncRedisCache:
        settings = get_settings().cache
        return cls(
            host=settings.host,
            port=settings.port,
            db=settings.db if db is None else db,
            password=settings.password,
            encoding=settings.encoding,
            decode_responses=settings.decode_responses,
            socket_timeout=settings.socket_timeout,
            socket_connect_timeout=settings.socket_connect_timeout,
        )

    @property
    def client(self) -> Any:
        return self._client

    def set(self, key: str, value: Any, ttl: int | None = None, **kwargs: Any) -> Any:
        ex = kwargs.pop("ex", None)
        if ttl is not None and ex is None:
            ex = ttl
        return self._client.set(key, value, ex=ex, **kwargs)

    def get(self, key: str) -> Any:
        return self._client.get(key)

    def delete(self, *keys: str) -> Any:
        return self._client.delete(*keys)

    def exists(self, key: str) -> Any:
        return self._client.exists(key)

    def incr(self, key: str, amount: int = 1) -> Any:
        return self._client.incr(key, amount=amount)

    def expire(self, key: str, ttl: int) -> Any:
        return self._client.expire(key, ttl)

    def eval(self, script: str, numkeys: int, *args: Any) -> Any:
        return self._client.eval(script, numkeys, *args)

    def hset(self, key: str, *args: Any, **kwargs: Any) -> Any:
        return self._client.hset(key, *args, **kwargs)

    def hgetall(self, key: str) -> dict[str, Any]:
        payload = self._client.hgetall(key)
        if isinstance(payload, dict):
            return {str(k): v for k, v in payload.items()}
        return {}


def resolve_sync_redis_client(
    redis_client: Any | None = None,
    *,
    db: int | None = None,
) -> Any:
    if redis_client is not None:
        return SyncRedisCache(client=redis_client).client
    return SyncRedisCache.from_settings(db=db).client
