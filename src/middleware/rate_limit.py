import asyncio
import inspect
import json
import time
from typing import Callable
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

from src import cache as cache_module
from src.cache import CacheProtocol, RedisCache, get_cache
from src.config import get_settings
from src.config.rate_limit import RateLimitSettings
from src.shared.errors import ErrorCode


class RateLimitMiddleware(BaseHTTPMiddleware):
    DOC_PATH_PREFIXES = ("/docs", "/redoc", "/openapi", "/health")

    def __init__(
        self,
        app,
        redis_client: Redis | None = None,
        settings: RateLimitSettings | None = None,
        client_identifier: Callable[[Request], str] | None = None,
    ):
        super().__init__(app)
        self._redis = redis_client
        self._settings = settings
        self._client_identifier = client_identifier or self._default_client_identifier
        self._cache_locks: dict[str, asyncio.Lock] = {}

    def _default_client_identifier(self, request: Request) -> str:
        return request.client.host if request.client else "unknown"

    async def _resolve_backend(self, request: Request) -> Redis | CacheProtocol | None:
        if self._redis is not None:
            return self._redis

        request_redis = getattr(request.state, "redis", None)
        if request_redis is not None:
            return request_redis

        app_redis = getattr(request.app.state, "redis", None)
        if app_redis is not None:
            return app_redis

        override = request.app.dependency_overrides.get(get_cache)
        if override is not None:
            resolved = override()
            if inspect.isasyncgen(resolved):
                try:
                    return await resolved.__anext__()
                finally:
                    await resolved.aclose()
            if inspect.isawaitable(resolved):
                return await resolved
            return resolved

        return cache_module.cache

    async def _sliding_window(
        self,
        client_id: str,
        endpoint: str,
        limit: int,
        window: float,
        redis: Redis,
    ) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window
        key = f"rate_limit:{endpoint}:{client_id}"
        member = f"{time.time_ns()}:{uuid4().hex}"

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, "-inf", str(window_start))
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.expire(key, int(window) + 1)
        results = await pipe.execute()

        current_count = results[2]
        remaining = max(limit - current_count, 0)
        return current_count >= limit, remaining

    async def _cache_sliding_window(
        self,
        client_id: str,
        endpoint: str,
        limit: int,
        window: float,
        cache: CacheProtocol,
    ) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window
        key = f"rate_limit:{endpoint}:{client_id}"
        lock = self._cache_locks.setdefault(key, asyncio.Lock())
        async with lock:
            raw = await cache.get(key)
            timestamps = json.loads(raw) if raw else []
            timestamps = [ts for ts in timestamps if ts > window_start]
            timestamps.append(now)
            await cache.set(key, json.dumps(timestamps), ttl=int(window) + 1)

            current_count = len(timestamps)
            remaining = max(limit - current_count, 0)
            return current_count >= limit, remaining

    async def _apply_limit(
        self,
        client_id: str,
        endpoint: str,
        limit: int,
        window: float,
        backend: Redis | CacheProtocol,
    ) -> tuple[bool, int]:
        if isinstance(backend, Redis) or hasattr(backend, "pipeline"):
            return await self._sliding_window(
                client_id, endpoint, limit, window, backend
            )

        if isinstance(backend, RedisCache):
            return await self._sliding_window(
                client_id, endpoint, limit, window, backend.client
            )

        return await self._cache_sliding_window(
            client_id, endpoint, limit, window, backend
        )

    def _backend_unavailable_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "code": int(ErrorCode.SYS_INTERNAL_ERROR),
                "msg": "Rate limit backend unavailable",
                "data": None,
            },
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        settings = self._settings or get_settings().rate_limit

        if not settings.enabled:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(prefix) for prefix in self.DOC_PATH_PREFIXES):
            return await call_next(request)

        endpoint = path
        endpoint_config = settings.get_endpoint(path)
        limit = endpoint_config.limit if endpoint_config else settings.global_limit
        window = endpoint_config.window if endpoint_config else settings.global_window

        client_id = self._client_identifier(request)
        backend = await self._resolve_backend(request)
        if backend is None:
            if endpoint_config is not None:
                return self._backend_unavailable_response()
            return await call_next(request)

        try:
            is_limited, remaining = await self._apply_limit(
                client_id, endpoint, limit, window, backend
            )
        except (
            RedisError,
            AttributeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            if endpoint_config is not None:
                return self._backend_unavailable_response()
            return await call_next(request)

        response = await call_next(request) if not is_limited else None

        if is_limited:
            response = JSONResponse(
                status_code=429,
                content={"code": 42901, "msg": "Rate limit exceeded", "data": None},
            )
            response.headers["Retry-After"] = str(int(window))

        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(window)

        return response
