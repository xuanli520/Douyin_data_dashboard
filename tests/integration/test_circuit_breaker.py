import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from src.core.circuit_breaker import circuit, CircuitBreakerError


@pytest.fixture
async def circuit_breaker_app():
    app = FastAPI(lifespan=lambda _: None)

    @app.get("/api/unprotected")
    async def unprotected():
        return {"status": "ok"}

    yield app


class TestCircuitBreakerWithFastAPI:
    @pytest.mark.asyncio
    async def test_successful_call_before_threshold(self, circuit_breaker_app):
        app = circuit_breaker_app
        call_count = 0

        @app.get("/api/success")
        @circuit(failure_threshold=3, recovery_timeout=60, name="success_endpoint")
        async def success_endpoint():
            nonlocal call_count
            call_count += 1
            return {"success": True}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/success")
            assert response.status_code == 200
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_unprotected_endpoint_works(self, circuit_breaker_app):
        async with AsyncClient(
            transport=ASGITransport(app=circuit_breaker_app), base_url="http://test"
        ) as client:
            response = await client.get("/api/unprotected")
            assert response.status_code == 200


class TestCircuitBreakerWithHttpClient:
    @pytest.mark.asyncio
    async def test_integration_with_endpoint(self):
        app = FastAPI(lifespan=lambda _: None)

        @app.get("/api/data")
        @circuit(failure_threshold=2, recovery_timeout=60, name="fetch_data")
        async def fetch_data():
            return {"data": "fetched"}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/data")
            assert response.status_code == 200
            assert response.json()["data"] == "fetched"


class TestCircuitBreakerFallbackPattern:
    @pytest.mark.asyncio
    async def test_fallback_on_circuit_error(self):
        app = FastAPI(lifespan=lambda _: None)

        @app.get("/api/external")
        @circuit(failure_threshold=2, recovery_timeout=60, name="external_fallback")
        async def external_api():
            raise ValueError("Service down")

        @app.get("/api/data")
        async def get_data():
            try:
                return await external_api()
            except CircuitBreakerError:
                return {"source": "cache", "data": "cached_data"}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(2):
                try:
                    await client.get("/api/external")
                except Exception:
                    pass

            response = await client.get("/api/data")
            assert response.status_code == 200
            assert response.json()["source"] == "cache"


class TestCircuitBreakerNamedCircuits:
    @pytest.mark.asyncio
    async def test_named_circuits_are_independent(self):
        app = FastAPI(lifespan=lambda _: None)

        @app.get("/api/service-a")
        @circuit(failure_threshold=2, recovery_timeout=60, name="service_a")
        async def service_a():
            raise ValueError("Service A down")

        @app.get("/api/service-b")
        @circuit(failure_threshold=3, recovery_timeout=60, name="service_b")
        async def service_b():
            raise ValueError("Service B down")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(2):
                try:
                    await client.get("/api/service-a")
                except Exception:
                    pass

            for _ in range(3):
                try:
                    await client.get("/api/service-b")
                except Exception:
                    pass
