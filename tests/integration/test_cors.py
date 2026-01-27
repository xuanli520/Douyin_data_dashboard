import pytest
from httpx import ASGITransport, AsyncClient

from src.middleware.cors import get_cors_middleware


@pytest.fixture
def cors_app():
    from fastapi import FastAPI

    app = FastAPI(
        lifespan=lambda _: None,
        middleware=[get_cors_middleware()],
    )

    @app.get("/api/data")
    async def get_data():
        return {"message": "ok"}

    return app


class TestCorsIntegration:
    @pytest.mark.asyncio
    async def test_preflight_allows_configured_origin(self, cors_app):
        async with AsyncClient(
            transport=ASGITransport(app=cors_app), base_url="http://localhost"
        ) as client:
            response = await client.options(
                "/api/data",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "X-Test",
                },
            )

            assert response.status_code == 200
            assert (
                response.headers["access-control-allow-origin"]
                == "http://localhost:3000"
            )
            assert response.headers["access-control-allow-credentials"] == "true"
            assert "GET" in response.headers["access-control-allow-methods"]
            assert "X-Test" in response.headers["access-control-allow-headers"]

    @pytest.mark.asyncio
    async def test_actual_request_includes_cors_headers(self, cors_app):
        async with AsyncClient(
            transport=ASGITransport(app=cors_app), base_url="http://localhost"
        ) as client:
            response = await client.get(
                "/api/data", headers={"Origin": "http://localhost:3000"}
            )

            assert response.status_code == 200
            assert (
                response.headers["access-control-allow-origin"]
                == "http://localhost:3000"
            )
            assert response.headers["access-control-allow-credentials"] == "true"

    @pytest.mark.asyncio
    async def test_preflight_disallowed_origin_rejected(self, cors_app):
        async with AsyncClient(
            transport=ASGITransport(app=cors_app), base_url="http://localhost"
        ) as client:
            response = await client.options(
                "/api/data",
                headers={
                    "Origin": "http://evil.com",
                    "Access-Control-Request-Method": "GET",
                },
            )

            assert response.status_code == 400
            headers_lower = {k.lower(): v for k, v in response.headers.items()}
            assert "access-control-allow-origin" not in headers_lower
