"""Integration tests for data source API endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport

from src.auth.models import User, UserRole


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
    """Create test authenticated user with admin role"""
    from fastapi_users.password import PasswordHelper
    from sqlalchemy import text

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

    role_result = await test_session.execute(
        text("SELECT id FROM roles WHERE name = 'admin'")
    )
    admin_role_id = role_result.scalar()

    if admin_role_id is None:
        await test_session.execute(
            text(
                "INSERT INTO roles (name, description, is_system) VALUES ('admin', 'Admin role', true)"
            )
        )
        await test_session.commit()
        role_result = await test_session.execute(
            text("SELECT id FROM roles WHERE name = 'admin'")
        )
        admin_role_id = role_result.scalar()

    assert admin_role_id is not None

    user_role = UserRole(user_id=user.id, role_id=admin_role_id)
    test_session.add(user_role)
    await test_session.commit()

    return user

    user_role = UserRole(user_id=user.id, role_id=admin_role_id)
    test_session.add(user_role)
    await test_session.commit()

    return user


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


class TestDataSourceAPI:
    async def test_create_data_source(self, test_client):
        response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Test Douyin Shop",
                "type": "DOUYIN_API",
                "config": {"api_key": "test_key", "api_secret": "test_secret"},
                "description": "Test data source",
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Test Douyin Shop"
        assert data["type"] == "DOUYIN_API"

    async def test_list_data_sources(self, test_client):
        response = await test_client.get("/api/v1/data-sources")
        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data, dict)
        assert "items" in data
        assert "total" in data

    async def test_get_data_source_detail(self, test_client):
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Test DS",
                "type": "DOUYIN_API",
                "config": {"api_key": "test_key", "api_secret": "test_secret"},
            },
        )
        ds_id = create_response.json()["data"]["id"]

        response = await test_client.get(f"/api/v1/data-sources/{ds_id}")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == ds_id

    async def test_update_data_source(self, test_client):
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Test DS",
                "type": "DOUYIN_API",
                "config": {"api_key": "test_key", "api_secret": "test_secret"},
            },
        )
        ds_id = create_response.json()["data"]["id"]

        response = await test_client.put(
            f"/api/v1/data-sources/{ds_id}",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Name"

    async def test_delete_data_source(self, test_client):
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Test DS to Delete",
                "type": "DOUYIN_API",
                "config": {"api_key": "test_key", "api_secret": "test_secret"},
            },
        )
        ds_id = create_response.json()["data"]["id"]

        response = await test_client.delete(f"/api/v1/data-sources/{ds_id}")
        assert response.status_code == 200


class TestScrapingRuleAPI:
    async def test_create_scraping_rule(self, test_client):
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Test DS",
                "type": "DOUYIN_API",
                "config": {"api_key": "test_key", "api_secret": "test_secret"},
            },
        )
        ds_id = ds_response.json()["data"]["id"]

        response = await test_client.post(
            "/api/v1/scraping-rules",
            json={
                "name": "Test Rule",
                "data_source_id": ds_id,
                "target_type": "ORDER_FULFILLMENT",
                "config": {"batch_size": 100},
                "schedule": "0 */6 * * *",
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Test Rule"
        assert data["data_source_id"] == ds_id

    async def test_list_scraping_rules_by_data_source(self, test_client):
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Test DS",
                "type": "DOUYIN_API",
                "config": {"api_key": "test_key", "api_secret": "test_secret"},
            },
        )
        ds_id = ds_response.json()["data"]["id"]

        response = await test_client.get(f"/api/v1/data-sources/{ds_id}/scraping-rules")
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)


class TestDataImportAPI:
    async def test_upload_file(self, test_client):
        import os

        os.makedirs("uploads/imports", exist_ok=True)

        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Import Test DS",
                "type": "FILE_UPLOAD",
                "config": {"path": "/uploads"},
            },
        )
        if ds_response.status_code != 200:
            print(f"DS create error: {ds_response.text}")
        assert ds_response.status_code == 200
        ds_id = ds_response.json()["data"]["id"]

        response = await test_client.post(
            "/api/v1/data-import/upload",
            files={"file": ("test.csv", b"col1,col2\nval1,val2", "text/csv")},
            data={"data_source_id": ds_id},
        )
        if response.status_code != 200:
            print(f"Upload error: {response.text}")
        assert response.status_code == 200
        assert "id" in response.json().get("data", {})

    async def test_parse_file(self, test_client):
        import os

        os.makedirs("uploads/imports", exist_ok=True)

        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Import Test DS",
                "type": "FILE_UPLOAD",
                "config": {"path": "/uploads"},
            },
        )
        assert ds_response.status_code == 200
        ds_id = ds_response.json()["data"]["id"]

        upload_response = await test_client.post(
            "/api/v1/data-import/upload",
            files={"file": ("test.csv", b"col1,col2\nval1,val2", "text/csv")},
            data={"data_source_id": ds_id},
        )
        assert upload_response.status_code == 200
        import_id = upload_response.json()["data"]["id"]

        response = await test_client.post(
            "/api/v1/data-import/parse", params={"import_id": import_id}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert "total_rows" in data
        assert "preview" in data

    async def test_validate_data(self, test_client):
        import os

        os.makedirs("uploads/imports", exist_ok=True)

        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Import Test DS",
                "type": "FILE_UPLOAD",
                "config": {"path": "/uploads"},
            },
        )
        assert ds_response.status_code == 200
        ds_id = ds_response.json()["data"]["id"]

        upload_response = await test_client.post(
            "/api/v1/data-import/upload",
            files={"file": ("test.csv", b"col1,col2\nval1,val2", "text/csv")},
            data={"data_source_id": ds_id},
        )
        assert upload_response.status_code == 200
        import_id = upload_response.json()["data"]["id"]

        await test_client.post(
            "/api/v1/data-import/parse", params={"import_id": import_id}
        )

        response = await test_client.post(
            "/api/v1/data-import/validate",
            params={"import_id": import_id},
            data={"data_type": "order"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert "total_rows" in data
        assert "passed" in data
        assert "failed" in data

    async def test_confirm_import(self, test_client):
        import os

        os.makedirs("uploads/imports", exist_ok=True)

        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Import Test DS",
                "type": "FILE_UPLOAD",
                "config": {"path": "/uploads"},
            },
        )
        assert ds_response.status_code == 200
        ds_id = ds_response.json()["data"]["id"]

        upload_response = await test_client.post(
            "/api/v1/data-import/upload",
            files={"file": ("test.csv", b"col1,col2\nval1,val2", "text/csv")},
            data={"data_source_id": ds_id},
        )
        assert upload_response.status_code == 200
        import_id = upload_response.json()["data"]["id"]

        await test_client.post(
            "/api/v1/data-import/parse", params={"import_id": import_id}
        )

        await test_client.post(
            "/api/v1/data-import/validate",
            params={"import_id": import_id},
            data={"data_type": "order"},
        )

        response = await test_client.post(
            "/api/v1/data-import/confirm", params={"import_id": import_id}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert "total" in data
        assert "success" in data
        assert "failed" in data

    async def test_get_import_history(self, test_client):
        response = await test_client.get("/api/v1/data-import/history")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "items" in data
        assert isinstance(data["items"], list)


class TestTaskAPI:
    async def test_list_tasks(self, test_client):
        response = await test_client.get("/api/v1/tasks")
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)

    async def test_create_task(self, test_client):
        response = await test_client.post(
            "/api/v1/tasks",
            json={
                "name": "Test Task",
                "task_type": "ORDER_COLLECTION",
                "data_source_id": 1,
                "schedule": "0 */6 * * *",
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Test Task"

    async def test_run_task(self, test_client):
        create_response = await test_client.post(
            "/api/v1/tasks",
            json={
                "name": "Test Task",
                "task_type": "ORDER_COLLECTION",
                "data_source_id": 1,
            },
        )
        task_id = create_response.json()["data"]["id"]

        response = await test_client.post(f"/api/v1/tasks/{task_id}/run")
        assert response.status_code == 200
        assert "execution_id" in response.json()["data"]

    async def test_get_task_executions(self, test_client):
        create_response = await test_client.post(
            "/api/v1/tasks",
            json={
                "name": "Test Task",
                "task_type": "ORDER_COLLECTION",
                "data_source_id": 1,
            },
        )
        task_id = create_response.json()["data"]["id"]

        response = await test_client.get(f"/api/v1/tasks/{task_id}/executions")
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)
