import json
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi_pagination import add_pagination
from httpx import ASGITransport, AsyncClient
from starlette.middleware import Middleware

from src.auth.models import User, UserRole


class MockCaptchaService:
    async def verify(self, captcha_verify_param: str) -> bool:
        return True


@pytest.fixture
async def test_session(test_db):
    async with test_db() as session:
        yield session


@pytest.fixture
async def authenticated_user(test_session):
    from fastapi_users.password import PasswordHelper

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("user123")

    user = User(
        username="loginstate_user",
        email="loginstate_user@test.com",
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=False,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)

    user_role = UserRole(user_id=user.id, role_id=1)
    test_session.add(user_role)
    await test_session.commit()

    yield user


@pytest.fixture
async def auth_token(authenticated_user):
    from src.auth.backend import get_jwt_strategy
    from src.config import get_settings

    settings = get_settings()
    strategy = get_jwt_strategy(settings)
    return await strategy.write_token(authenticated_user)


@pytest.fixture
async def test_client(test_db, test_session, auth_token):
    from src.api import (
        admin_router,
        auth_router,
        core_router,
        create_oauth_router,
        data_import_router,
        data_source_router,
        monitor_router,
        scraping_rule_router,
        task_router,
    )
    from src.auth.captcha import get_captcha_service
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
    app.dependency_overrides[get_captcha_service] = lambda: MockCaptchaService()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {auth_token}"
        yield client


pytestmark = pytest.mark.asyncio


async def test_upload_shop_dashboard_login_state(test_client):
    create_response = await test_client.post(
        "/api/v1/data-sources",
        json={
            "name": "LoginState DS",
            "type": "DOUYIN_SHOP",
            "config": {},
        },
    )
    assert create_response.status_code == 200
    ds_id = create_response.json()["data"]["id"]

    storage_state = {
        "cookies": [{"name": "sid", "value": "token"}],
        "origins": [],
    }
    response = await test_client.post(
        f"/api/v1/data-sources/{ds_id}/shop-dashboard/login-state",
        data={"account_id": "acct-1"},
        files={
            "file": (
                "storage_state.json",
                json.dumps(storage_state, ensure_ascii=False),
                "application/json",
            )
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["config"]["shop_dashboard_login_state_meta"]["cookie_count"] == 1
    assert data["config"]["shop_dashboard_login_state_meta"]["account_id"] == "acct-1"
    assert "shop_dashboard_login_state" not in data["config"]


async def test_clear_shop_dashboard_login_state(test_client):
    create_response = await test_client.post(
        "/api/v1/data-sources",
        json={
            "name": "LoginState Clear DS",
            "type": "DOUYIN_SHOP",
            "config": {},
        },
    )
    assert create_response.status_code == 200
    ds_id = create_response.json()["data"]["id"]

    await test_client.post(
        f"/api/v1/data-sources/{ds_id}/shop-dashboard/login-state",
        data={"account_id": "acct-1"},
        files={
            "file": (
                "storage_state.json",
                json.dumps(
                    {
                        "cookies": [{"name": "sid", "value": "token"}],
                        "origins": [],
                    },
                    ensure_ascii=False,
                ),
                "application/json",
            )
        },
    )

    response = await test_client.delete(
        f"/api/v1/data-sources/{ds_id}/shop-dashboard/login-state"
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "shop_dashboard_login_state_meta" not in data["config"]
    assert "shop_dashboard_login_state" not in data["config"]
