import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from src.config.rate_limit import RateLimitEndpoint, RateLimitSettings
from src.middleware.rate_limit import RateLimitMiddleware


class MockRedis:
    def __init__(self):
        self.data = {}

    def pipeline(self):
        return MockPipeline(self)


class MockPipeline:
    def __init__(self, redis):
        self.redis = redis
        self.commands = []

    def zremrangebyscore(self, key, min_score, max_score):
        self.commands.append(("zremrangebyscore", key, min_score, max_score))
        return self

    def zadd(self, key, mapping):
        self.commands.append(("zadd", key, mapping))
        return self

    def zcard(self, key):
        self.commands.append(("zcard", key))
        return self

    def expire(self, key, ttl):
        self.commands.append(("expire", key, ttl))
        return self

    async def execute(self):
        results = []
        for cmd in self.commands:
            if cmd[0] == "zremrangebyscore":
                key = cmd[1]
                if key not in self.redis.data:
                    self.redis.data[key] = []
                self.redis.data[key] = [
                    (s, t) for s, t in self.redis.data[key]
                    if float(s) >= float(cmd[2])
                ]
                results.append(0)
            elif cmd[0] == "zadd":
                key = cmd[1]
                if key not in self.redis.data:
                    self.redis.data[key] = []
                for score, member in cmd[2].items():
                    self.redis.data[key].append((score, member))
                results.append(1)
            elif cmd[0] == "zcard":
                key = cmd[1]
                results.append(len(self.redis.data.get(key, [])))
            elif cmd[0] == "expire":
                results.append(True)
        return results


def create_mock_request(path: str, client_host: str = "127.0.0.1", forwarded_for: str | None = None):
    request = MagicMock(spec=Request)
    request.url.path = path
    request.client.host = client_host
    if forwarded_for:
        request.headers = {"X-Forwarded-For": forwarded_for}
    else:
        request.headers = {}
    return request


class TestSlidingWindow:
    @pytest.mark.asyncio
    async def test_sliding_window_under_limit(self):
        settings = RateLimitSettings(
            enabled=True,
            global_limit=10,
            global_window=60,
        )
        redis = MockRedis()
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=redis, settings=settings)

        async def mock_call_next(req):
            return Response(status_code=200)

        request = create_mock_request("/api/test")
        request.state.redis = redis

        for i in range(5):
            response = await middleware.dispatch(request, mock_call_next)
            assert response.status_code == 200
            remaining = int(response.headers["X-RateLimit-Remaining"])
            assert remaining == 10 - i - 1

    @pytest.mark.asyncio
    async def test_sliding_window_exceeds_limit(self):
        settings = RateLimitSettings(
            enabled=True,
            global_limit=3,
            global_window=60,
        )
        redis = MockRedis()
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=redis, settings=settings)

        async def mock_call_next(req):
            return Response(status_code=200)

        request = create_mock_request("/api/test")
        request.state.redis = redis

        for i in range(2):
            response = await middleware.dispatch(request, mock_call_next)
            assert response.status_code == 200

        response = await middleware.dispatch(request, mock_call_next)
        assert response.status_code == 429
        assert response.headers["X-RateLimit-Limit"] == "3"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert "Retry-After" in response.headers


class TestClientIdentifier:
    @pytest.mark.asyncio
    async def test_client_identifier_forwarded_for(self):
        settings = RateLimitSettings(enabled=True)
        middleware = RateLimitMiddleware(app=MagicMock(), settings=settings)

        request = create_mock_request("/api/test", forwarded_for="192.168.1.100, 10.0.0.1")
        client_id = middleware._default_client_identifier(request)
        assert client_id == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_client_identifier_direct_ip(self):
        settings = RateLimitSettings(enabled=True)
        middleware = RateLimitMiddleware(app=MagicMock(), settings=settings)

        request = create_mock_request("/api/test", client_host="10.0.0.50")
        client_id = middleware._default_client_identifier(request)
        assert client_id == "10.0.0.50"

    @pytest.mark.asyncio
    async def test_client_identifier_unknown(self):
        settings = RateLimitSettings(enabled=True)
        middleware = RateLimitMiddleware(app=MagicMock(), settings=settings)

        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = None
        client_id = middleware._default_client_identifier(request)
        assert client_id == "unknown"


class TestSkipDocsPaths:
    @pytest.mark.asyncio
    async def test_skip_docs_paths(self):
        settings = RateLimitSettings(
            enabled=True,
            global_limit=1,
            global_window=60,
        )
        redis = MockRedis()
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=redis, settings=settings)

        call_next_called = False

        async def mock_call_next(req):
            nonlocal call_next_called
            call_next_called = True
            return Response(status_code=200)

        for path in ["/docs", "/redoc", "/openapi"]:
            request = create_mock_request(path)
            request.state.redis = redis
            call_next_called = False

            response = await middleware.dispatch(request, mock_call_next)

            assert call_next_called is True
            assert response.status_code == 200
            assert "X-RateLimit-Limit" not in response.headers


class TestRateLimitSettings:
    def test_default_settings(self):
        settings = RateLimitSettings()
        assert settings.enabled is True
        assert settings.global_limit == 1000
        assert settings.global_window == 60
        assert settings.endpoints == {}

    def test_endpoint_config(self):
        endpoint = RateLimitEndpoint(limit=10, window=30)
        settings = RateLimitSettings(
            global_limit=100,
            endpoints={"/api/secure": endpoint},
        )
        assert settings.global_limit == 100
        assert settings.endpoints["/api/secure"].limit == 10
        assert settings.endpoints["/api/secure"].window == 30


class TestDisabledRateLimit:
    @pytest.mark.asyncio
    async def test_disabled_rate_limit(self):
        settings = RateLimitSettings(enabled=False)
        redis = MockRedis()
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=redis, settings=settings)

        call_next_called = False

        async def mock_call_next(req):
            nonlocal call_next_called
            call_next_called = True
            return Response(status_code=200)

        request = create_mock_request("/api/test")
        request.state.redis = redis

        response = await middleware.dispatch(request, mock_call_next)

        assert call_next_called is True
        assert response.status_code == 200
