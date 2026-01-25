import time
from typing import Callable

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.config import get_settings
from src.config.rate_limit import RateLimitSettings


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

    def _default_client_identifier(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def _sliding_window(
        self,
        client_id: str,
        endpoint: str,
        limit: int,
        window: int,
        redis: Redis,
    ) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window
        key = f"rate_limit:{endpoint}:{client_id}"

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, "-inf", str(window_start))
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, int(window) + 1)
        results = await pipe.execute()

        current_count = results[2]
        remaining = limit - current_count
        return current_count >= limit, remaining

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        settings = self._settings or get_settings().rate_limit

        if not settings.enabled:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(prefix) for prefix in self.DOC_PATH_PREFIXES):
            return await call_next(request)

        endpoint = path
        endpoint_config = settings.endpoints.get(path)
        limit = endpoint_config.limit if endpoint_config else settings.global_limit
        window = endpoint_config.window if endpoint_config else settings.global_window

        client_id = self._client_identifier(request)
        redis = self._redis
        if redis is None:
            try:
                redis = request.state.redis
            except AttributeError:
                pass

        if redis is None:
            return await call_next(request)

        is_limited, remaining = await self._sliding_window(
            client_id, endpoint, limit, window, redis
        )

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
