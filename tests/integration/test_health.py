import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncEngine

from src.api.core import router as core_router, get_engine
from src.cache import get_cache
from src.responses import ResponseWrapperMiddleware
from src.handlers import register_exception_handlers
from src.auth.models import User


@pytest.fixture
def mock_current_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.email = "test@example.com"
    user.is_active = True
    user.is_superuser = False
    return user


@pytest.fixture
def health_app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(core_router)
    return test_app


@pytest.fixture
def app_with_handlers(health_app: FastAPI, mock_current_user: User) -> FastAPI:
    from src.auth import current_user

    health_app.add_middleware(ResponseWrapperMiddleware)
    register_exception_handlers(health_app)
    health_app.dependency_overrides[current_user] = lambda: mock_current_user
    return health_app


@pytest.fixture
def mock_engine():
    mock = MagicMock(spec=AsyncEngine)
    conn_mock = AsyncMock()
    conn_mock.__aenter__ = AsyncMock(return_value=conn_mock)
    mock.connect.return_value = conn_mock
    return mock, conn_mock


@pytest.fixture
def mock_cache():
    mock = MagicMock()
    mock.client.ping = AsyncMock(return_value=True)
    return mock


@pytest.mark.asyncio
async def test_health_check_returns_raw_json(
    app_with_handlers: FastAPI, mock_engine, mock_cache
):
    engine, _ = mock_engine
    cache = mock_cache

    async def override_get_cache():
        yield cache

    app_with_handlers.dependency_overrides[get_cache] = override_get_cache
    app_with_handlers.dependency_overrides[get_engine] = lambda: engine

    async with AsyncClient(
        transport=ASGITransport(app=app_with_handlers), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "components" in data
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_check_contains_components(
    app_with_handlers: FastAPI, mock_engine, mock_cache
):
    engine, _ = mock_engine
    cache = mock_cache

    async def override_get_cache():
        yield cache

    app_with_handlers.dependency_overrides[get_cache] = override_get_cache
    app_with_handlers.dependency_overrides[get_engine] = lambda: engine

    async with AsyncClient(
        transport=ASGITransport(app=app_with_handlers), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        data = response.json()
        assert "database" in data["components"]
        assert "redis" in data["components"]


@pytest.mark.asyncio
async def test_health_check_healthy_status(
    app_with_handlers: FastAPI, mock_engine, mock_cache
):
    engine, _ = mock_engine
    cache = mock_cache

    async def override_get_cache():
        yield cache

    app_with_handlers.dependency_overrides[get_cache] = override_get_cache
    app_with_handlers.dependency_overrides[get_engine] = lambda: engine

    async with AsyncClient(
        transport=ASGITransport(app=app_with_handlers), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["components"]["database"]["status"] == "healthy"
        assert data["components"]["redis"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_has_latency_metrics(
    app_with_handlers: FastAPI, mock_engine, mock_cache
):
    engine, _ = mock_engine
    cache = mock_cache

    async def override_get_cache():
        yield cache

    app_with_handlers.dependency_overrides[get_cache] = override_get_cache
    app_with_handlers.dependency_overrides[get_engine] = lambda: engine

    async with AsyncClient(
        transport=ASGITransport(app=app_with_handlers), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        data = response.json()
        assert "latency_ms" in data["components"]["database"]
        assert "latency_ms" in data["components"]["redis"]


@pytest.mark.asyncio
async def test_health_check_unhealthy_when_all_failed(
    app_with_handlers: FastAPI, mock_engine, mock_cache
):
    engine, conn = mock_engine
    cache = mock_cache

    conn.execute = AsyncMock(side_effect=Exception("DB error"))
    cache.client.ping = AsyncMock(side_effect=Exception("Redis error"))

    async def override_get_cache():
        yield cache

    app_with_handlers.dependency_overrides[get_cache] = override_get_cache
    app_with_handlers.dependency_overrides[get_engine] = lambda: engine

    async with AsyncClient(
        transport=ASGITransport(app=app_with_handlers), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["components"]["database"]["status"] == "unhealthy"
        assert data["components"]["redis"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_health_check_degraded_when_db_failed(
    app_with_handlers: FastAPI, mock_engine, mock_cache
):
    engine, conn = mock_engine
    cache = mock_cache

    conn.execute = AsyncMock(side_effect=Exception("DB error"))

    async def override_get_cache():
        yield cache

    app_with_handlers.dependency_overrides[get_cache] = override_get_cache
    app_with_handlers.dependency_overrides[get_engine] = lambda: engine

    async with AsyncClient(
        transport=ASGITransport(app=app_with_handlers), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["components"]["database"]["status"] == "unhealthy"
        assert data["components"]["redis"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_degraded_when_redis_failed(
    app_with_handlers: FastAPI, mock_engine, mock_cache
):
    engine, _ = mock_engine
    cache = mock_cache

    cache.client.ping = AsyncMock(side_effect=Exception("Redis error"))

    async def override_get_cache():
        yield cache

    app_with_handlers.dependency_overrides[get_cache] = override_get_cache
    app_with_handlers.dependency_overrides[get_engine] = lambda: engine

    async with AsyncClient(
        transport=ASGITransport(app=app_with_handlers), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["components"]["database"]["status"] == "healthy"
        assert data["components"]["redis"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_health_check_error_details_in_response(
    app_with_handlers: FastAPI, mock_engine, mock_cache
):
    engine, conn = mock_engine
    cache = mock_cache

    db_error = "Database connection failed"
    conn.execute = AsyncMock(side_effect=Exception(db_error))

    async def override_get_cache():
        yield cache

    app_with_handlers.dependency_overrides[get_cache] = override_get_cache
    app_with_handlers.dependency_overrides[get_engine] = lambda: engine

    async with AsyncClient(
        transport=ASGITransport(app=app_with_handlers), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        data = response.json()
        assert "error" in data["components"]["database"]
        assert db_error in data["components"]["database"]["error"]
