import pytest
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient

from src.config.rate_limit import RateLimitEndpoint, RateLimitSettings
from src.middleware.rate_limit import RateLimitMiddleware
from src.responses import ResponseWrapperMiddleware


@pytest.fixture
async def fake_redis():
    redis = FakeAsyncRedis(decode_responses=True)
    await redis.flushall()
    yield redis
    await redis.aclose()


@pytest.fixture
async def rate_limited_app(fake_redis):
    from fastapi import FastAPI
    from starlette.middleware import Middleware

    settings = RateLimitSettings(
        enabled=True,
        global_limit=5,
        global_window=60,
        endpoints={
            "/api/secure": RateLimitEndpoint(limit=2, window=60),
        },
    )

    app = FastAPI(
        lifespan=lambda _: None,
        middleware=[
            Middleware(ResponseWrapperMiddleware),
            Middleware(RateLimitMiddleware, redis_client=fake_redis, settings=settings),
        ],
    )

    @app.get("/api/core/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/secure")
    async def secure():
        return {"secure": True}

    yield app


class TestRateLimitHeaders:
    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, rate_limited_app, fake_redis):
        async with AsyncClient(
            transport=ASGITransport(app=rate_limited_app), base_url="http://test"
        ) as client:
            response = await client.get("/api/core/health")
            assert response.status_code == 200
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Window" in response.headers


class TestRateLimitExceeded:
    @pytest.mark.asyncio
    async def test_rate_limit_returns_429_when_exceeded(
        self, rate_limited_app, fake_redis
    ):
        async with AsyncClient(
            transport=ASGITransport(app=rate_limited_app), base_url="http://test"
        ) as client:
            for _ in range(5):
                await client.get("/api/core/health")

            response = await client.get("/api/core/health")
            assert response.status_code == 429
            assert response.json()["code"] == 42901
            assert response.headers["Retry-After"] == "60"

    @pytest.mark.asyncio
    async def test_endpoint_specific_limit(self, rate_limited_app, fake_redis):
        async with AsyncClient(
            transport=ASGITransport(app=rate_limited_app), base_url="http://test"
        ) as client:
            response = await client.get("/api/secure")
            assert response.status_code == 200
            assert response.headers["X-RateLimit-Limit"] == "2"

            response = await client.get("/api/secure")
            assert response.status_code == 429


class TestRateLimitPerClient:
    @pytest.mark.asyncio
    async def test_different_clients_have_separate_limits(self, fake_redis):
        from fastapi import FastAPI
        from starlette.middleware import Middleware

        settings = RateLimitSettings(enabled=True, global_limit=2, global_window=60)

        app = FastAPI(
            lifespan=lambda _: None,
            middleware=[
                Middleware(ResponseWrapperMiddleware),
                Middleware(
                    RateLimitMiddleware, redis_client=fake_redis, settings=settings
                ),
            ],
        )

        @app.get("/api/test")
        async def test():
            return {"status": "ok"}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client1:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client2:
                for _ in range(2):
                    response = await client1.get(
                        "/api/test", headers={"X-Forwarded-For": "192.168.1.1"}
                    )
                assert response.status_code == 429

                response = await client2.get(
                    "/api/test", headers={"X-Forwarded-For": "192.168.1.2"}
                )
                assert response.status_code == 200
