import re

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import Response

from src.middleware.monitor import MonitorMiddleware, generate_metrics
from src.responses import ResponseWrapperMiddleware


@pytest.fixture
def monitor_app():
    from fastapi import APIRouter, FastAPI
    from starlette.middleware import Middleware

    from src.handlers import register_exception_handlers

    app = FastAPI(
        lifespan=lambda _: None,
        middleware=[
            Middleware(ResponseWrapperMiddleware),
            Middleware(MonitorMiddleware),
        ],
    )

    register_exception_handlers(app)

    router = APIRouter()

    @router.get("/api/users")
    async def list_users():
        return [{"id": 1, "name": "John"}]

    @router.get("/api/users/{user_id}")
    async def get_user(user_id: int):
        return {"id": user_id, "name": "John"}

    @router.post("/api/users")
    async def create_user():
        return {"id": 2, "name": "Jane"}

    @router.get("/api/error")
    async def error_endpoint():
        raise ValueError("Test error")

    @router.get("/metrics")
    async def metrics():
        return Response(content=generate_metrics(), media_type="text/plain")

    app.include_router(router)
    return app


class TestMetricsEndpoint:
    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_prometheus_format(self, monitor_app):
        async with AsyncClient(
            transport=ASGITransport(app=monitor_app), base_url="http://test"
        ) as client:
            response = await client.get("/metrics")
            assert response.status_code == 200
            assert "text/plain" in response.headers["content-type"]
            text = response.text
            assert "# HELP" in text or "# TYPE" in text

    @pytest.mark.asyncio
    async def test_request_counter_increments(self, monitor_app):
        async with AsyncClient(
            transport=ASGITransport(app=monitor_app), base_url="http://test"
        ) as client:
            await client.get("/api/users")
            await client.get("/api/users")
            await client.get("/api/users")

            response = await client.get("/metrics")
            text = response.text

            assert 'http_requests_total{endpoint="/api/users",method="GET"' in text
            assert 'status_code="200"' in text


class TestRequestDuration:
    @pytest.mark.asyncio
    async def test_duration_histogram_recorded(self, monitor_app):
        async with AsyncClient(
            transport=ASGITransport(app=monitor_app), base_url="http://test"
        ) as client:
            await client.get("/api/users")

            response = await client.get("/metrics")
            text = response.text

            assert "http_request_duration_seconds_bucket{" in text
            assert "le=" in text


class TestRequestsInProgress:
    @pytest.mark.asyncio
    async def test_in_progress_gauge_recorded(self, monitor_app):
        async with AsyncClient(
            transport=ASGITransport(app=monitor_app), base_url="http://test"
        ) as client:
            await client.get("/api/users")

            response = await client.get("/metrics")
            text = response.text

            assert "http_requests_in_progress{" in text


class TestExceptionTracking:
    @pytest.mark.asyncio
    async def test_exceptions_tracked(self, monitor_app):
        async with AsyncClient(
            transport=ASGITransport(app=monitor_app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            try:
                await client.get("/api/error")
            except ValueError:
                pass

            response = await client.get("/metrics")
            text = response.text

            assert (
                'http_exceptions_total{endpoint="/api/error",exception_type="ValueError",method="GET"}'
                in text
            )


class TestPathNormalization:
    @pytest.mark.asyncio
    async def test_path_parameters_normalized(self, monitor_app):
        async with AsyncClient(
            transport=ASGITransport(app=monitor_app), base_url="http://test"
        ) as client:
            await client.get("/api/users/1")
            await client.get("/api/users/2")
            await client.get("/api/users/123")

            response = await client.get("/metrics")
            text = response.text

            matches = re.findall(
                r'http_requests_total\{endpoint="/api/users/\{\}"', text
            )
            assert len(matches) == 1


class TestDifferentMethods:
    @pytest.mark.asyncio
    async def test_get_method_tracked(self, monitor_app):
        async with AsyncClient(
            transport=ASGITransport(app=monitor_app), base_url="http://test"
        ) as client:
            await client.get("/api/users")

            response = await client.get("/metrics")
            text = response.text
            assert 'method="GET"' in text

    @pytest.mark.asyncio
    async def test_post_method_tracked(self, monitor_app):
        async with AsyncClient(
            transport=ASGITransport(app=monitor_app), base_url="http://test"
        ) as client:
            await client.post("/api/users")

            response = await client.get("/metrics")
            text = response.text
            assert 'method="POST"' in text


class TestStatusCodeTracking:
    @pytest.mark.asyncio
    async def test_200_status_code(self, monitor_app):
        async with AsyncClient(
            transport=ASGITransport(app=monitor_app), base_url="http://test"
        ) as client:
            response = await client.get("/api/users")
            assert response.status_code == 200

            metrics_response = await client.get("/metrics")
            text = metrics_response.text
            assert 'status_code="200"' in text
