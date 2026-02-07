"""Integration tests for data source schemas with API endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport

from src.domains.data_source.schemas import (
    DataSourceCreate,
    DataSourceStatus,
    DataSourceType,
    DataSourceUpdate,
    ScrapingRuleCreate,
    ScrapingRuleType,
    ScrapingRuleUpdate,
)


class MockCaptchaService:
    async def verify(self, captcha_verify_param: str) -> bool:
        return True


@pytest.fixture
async def test_session(test_db):
    """Get a shared test session for the test"""
    async with test_db() as session:
        yield session


@pytest.fixture
async def authenticated_user(test_session):
    """Create test authenticated user with admin role (role_id=1)"""
    from fastapi_users.password import PasswordHelper

    from src.auth.models import User, UserRole

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("user123")

    user = User(
        username="datauser",
        email="datauser@test.com",
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=False,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)

    assert user.id is not None, "User ID should be set after commit"
    user_role = UserRole(user_id=user.id, role_id=1)
    test_session.add(user_role)
    await test_session.commit()

    yield user


@pytest.fixture
async def auth_token(authenticated_user):
    """Generate auth token"""
    from src.auth.backend import get_jwt_strategy
    from src.config import get_settings

    settings = get_settings()
    strategy = get_jwt_strategy(settings)
    token = await strategy.write_token(authenticated_user)
    return token


@pytest.fixture
async def test_client(test_db, test_session, auth_token):
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from fastapi_pagination import add_pagination
    from starlette.middleware import Middleware

    from src.api import (
        auth_router,
        core_router,
        create_oauth_router,
        monitor_router,
        admin_router,
        data_source_router,
        scraping_rule_router,
        data_import_router,
        task_router,
    )
    from src.cache import close_cache, get_cache
    from src.config import get_settings
    from src.handlers import register_exception_handlers
    from src.middleware.cors import get_cors_middleware
    from src.middleware.monitor import MonitorMiddleware
    from src.middleware.rate_limit import RateLimitMiddleware
    from src.responses.middleware import ResponseWrapperMiddleware
    from src.session import close_db, get_session

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await close_cache()
        await close_db()

    settings = get_settings()

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        debug=settings.app.debug,
        lifespan=lifespan,
        middleware=[
            get_cors_middleware(),
            Middleware(ResponseWrapperMiddleware),
            Middleware(RateLimitMiddleware),
            Middleware(MonitorMiddleware),
        ],
    )

    register_exception_handlers(app)

    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(create_oauth_router(settings), prefix="/auth", tags=["auth"])
    app.include_router(core_router, tags=["core"])
    app.include_router(monitor_router, tags=["monitor"])
    app.include_router(admin_router, prefix="/api", tags=["admin"])
    app.include_router(data_source_router, prefix="/api/v1", tags=["data-source"])
    app.include_router(scraping_rule_router, prefix="/api/v1", tags=["scraping-rule"])
    app.include_router(data_import_router, prefix="/api/v1", tags=["data-import"])
    app.include_router(task_router, prefix="/api/v1", tags=["task"])

    add_pagination(app)

    async def override_get_session():
        yield test_session

    app.dependency_overrides[get_session] = override_get_session

    async def override_get_cache():
        from src.cache import LocalCache

        cache = LocalCache()
        yield cache

    app.dependency_overrides[get_cache] = override_get_cache

    from src.auth.captcha import get_captcha_service

    app.dependency_overrides[get_captcha_service] = lambda: MockCaptchaService()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {auth_token}"
        yield client


pytestmark = pytest.mark.asyncio


class TestDataSourceCreateSchema:
    async def test_create_endpoint_accepts_valid_schema(self, test_client):
        payload = DataSourceCreate(
            name="Test Douyin Shop",
            type=DataSourceType.DOUYIN_API,
            config={"api_key": "test_key", "api_secret": "test_secret"},
            description="Test data source for integration",
        )
        response = await test_client.post(
            "/api/v1/data-sources",
            json=payload.model_dump(),
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Test Douyin Shop"
        assert data["type"] == "DOUYIN_API"

    async def test_create_endpoint_rejects_invalid_type(self, test_client):
        response = await test_client.post(
            "/api/v1/data-sources",
            json={"name": "Test", "type": "invalid_type"},
        )
        assert response.status_code == 422

    async def test_create_endpoint_rejects_empty_name(self, test_client):
        response = await test_client.post(
            "/api/v1/data-sources",
            json={"name": "", "type": "DOUYIN_API"},
        )
        assert response.status_code == 422

    async def test_create_endpoint_rejects_long_description(self, test_client):
        response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Test",
                "type": "DOUYIN_API",
                "description": "x" * 501,
            },
        )
        assert response.status_code == 422


class TestDataSourceUpdateSchema:
    async def test_update_endpoint_accepts_partial_update(self, test_client):
        create_payload = DataSourceCreate(
            name="Original Name",
            type=DataSourceType.DATABASE,
        )
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json=create_payload.model_dump(),
        )
        ds_id = create_response.json()["data"]["id"]

        update_payload = DataSourceUpdate(name="Updated Name")
        response = await test_client.put(
            f"/api/v1/data-sources/{ds_id}",
            json=update_payload.model_dump(exclude_none=True),
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Name"

    async def test_update_endpoint_accepts_status_change(self, test_client):
        create_payload = DataSourceCreate(
            name="Test DS",
            type=DataSourceType.WEBHOOK,
            status=DataSourceStatus.ACTIVE,
        )
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json=create_payload.model_dump(),
        )
        ds_id = create_response.json()["data"]["id"]

        update_payload = DataSourceUpdate(status=DataSourceStatus.INACTIVE)
        response = await test_client.put(
            f"/api/v1/data-sources/{ds_id}",
            json=update_payload.model_dump(exclude_none=True),
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "INACTIVE"

    async def test_update_endpoint_accepts_config_update(self, test_client):
        create_payload = DataSourceCreate(
            name="Test DS",
            type=DataSourceType.DATABASE,
            config={"host": "old_host"},
        )
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json=create_payload.model_dump(),
        )
        ds_id = create_response.json()["data"]["id"]

        update_payload = DataSourceUpdate(config={"host": "new_host", "port": 5432})
        response = await test_client.put(
            f"/api/v1/data-sources/{ds_id}",
            json=update_payload.model_dump(exclude_none=True),
        )
        assert response.status_code == 200
        assert response.json()["data"]["config"]["host"] == "new_host"


class TestScrapingRuleCreateSchema:
    async def test_create_scraping_rule_endpoint(self, test_client):
        ds_payload = DataSourceCreate(
            name="Test DS",
            type=DataSourceType.DOUYIN_API,
            config={"api_key": "test_key", "api_secret": "test_secret"},
        )
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json=ds_payload.model_dump(),
        )
        ds_id = ds_response.json()["data"]["id"]

        rule_payload = ScrapingRuleCreate(
            data_source_id=ds_id,
            name="Order Collection Rule",
            rule_type=ScrapingRuleType.ORDERS,
            config={"batch_size": 100},
            schedule="0 */6 * * *",
            description="Collect orders every 6 hours",
        )
        response = await test_client.post(
            "/api/v1/scraping-rules",
            json=rule_payload.model_dump(),
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Order Collection Rule"
        assert data["rule_type"] == "ORDERS"
        assert data["data_source_id"] == ds_id

    async def test_create_scraping_rule_rejects_missing_data_source(self, test_client):
        rule_payload = ScrapingRuleCreate(
            data_source_id=99999,
            name="Test Rule",
            rule_type=ScrapingRuleType.PRODUCTS,
        )
        response = await test_client.post(
            "/api/v1/scraping-rules",
            json=rule_payload.model_dump(),
        )
        assert response.status_code == 404


class TestScrapingRuleUpdateSchema:
    async def test_update_scraping_rule_schedule(self, test_client):
        ds_payload = DataSourceCreate(
            name="Test DS",
            type=DataSourceType.DOUYIN_API,
            config={"api_key": "test_key", "api_secret": "test_secret"},
        )
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json=ds_payload.model_dump(),
        )
        ds_id = ds_response.json()["data"]["id"]

        rule_payload = ScrapingRuleCreate(
            data_source_id=ds_id,
            name="Test Rule",
            rule_type=ScrapingRuleType.ORDERS,
            schedule="0 0 * * *",
        )
        rule_response = await test_client.post(
            "/api/v1/scraping-rules",
            json=rule_payload.model_dump(),
        )
        rule_id = rule_response.json()["data"]["id"]

        update_payload = ScrapingRuleUpdate(schedule="0 */12 * * *")
        response = await test_client.put(
            f"/api/v1/scraping-rules/{rule_id}",
            json=update_payload.model_dump(exclude_none=True),
        )
        assert response.status_code == 200
        assert response.json()["data"]["schedule"] == "0 */12 * * *"

    async def test_update_scraping_rule_deactivation(self, test_client):
        ds_payload = DataSourceCreate(
            name="Test DS",
            type=DataSourceType.DOUYIN_API,
            config={"api_key": "test_key", "api_secret": "test_secret"},
        )
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json=ds_payload.model_dump(),
        )
        ds_id = ds_response.json()["data"]["id"]

        rule_payload = ScrapingRuleCreate(
            data_source_id=ds_id,
            name="Test Rule",
            rule_type=ScrapingRuleType.PRODUCTS,
            is_active=True,
        )
        rule_response = await test_client.post(
            "/api/v1/scraping-rules",
            json=rule_payload.model_dump(),
        )
        rule_id = rule_response.json()["data"]["id"]

        update_payload = ScrapingRuleUpdate(is_active=False)
        response = await test_client.put(
            f"/api/v1/scraping-rules/{rule_id}",
            json=update_payload.model_dump(exclude_none=True),
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_active"] is False


class TestSchemaResponseStructure:
    async def test_datasource_response_contains_all_fields(self, test_client):
        payload = DataSourceCreate(
            name="Full Field Test",
            type=DataSourceType.FILE_UPLOAD,
            config={"path": "/uploads"},
            status=DataSourceStatus.ACTIVE,
            description="Testing all response fields",
        )
        response = await test_client.post(
            "/api/v1/data-sources",
            json=payload.model_dump(),
        )
        assert response.status_code == 200
        data = response.json()["data"]

        required_fields = {
            "id",
            "name",
            "type",
            "config",
            "status",
            "description",
            "created_at",
            "updated_at",
        }
        assert required_fields.issubset(set(data.keys()))

    async def test_scraping_rule_response_contains_all_fields(self, test_client):
        ds_payload = DataSourceCreate(name="Test DS", type=DataSourceType.DATABASE)
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json=ds_payload.model_dump(),
        )
        ds_id = ds_response.json()["data"]["id"]

        rule_payload = ScrapingRuleCreate(
            data_source_id=ds_id,
            name="Field Test Rule",
            rule_type=ScrapingRuleType.USERS,
            config={"limit": 1000},
            schedule="0 0 * * 0",
            is_active=True,
            description="Testing all response fields",
        )
        response = await test_client.post(
            "/api/v1/scraping-rules",
            json=rule_payload.model_dump(),
        )
        assert response.status_code == 200
        data = response.json()["data"]

        required_fields = {
            "id",
            "data_source_id",
            "name",
            "rule_type",
            "config",
            "schedule",
            "is_active",
            "description",
            "created_at",
            "updated_at",
        }
        assert required_fields.issubset(set(data.keys()))
