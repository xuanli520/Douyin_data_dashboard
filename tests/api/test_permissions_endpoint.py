import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from src.cache import LocalCache, get_cache
from src.session import get_session
from src.auth.captcha import get_captcha_service
from src.auth.models import User
from src.auth.rbac import get_permission_service
from src.api.v1 import permissions as permissions_api
from src.main import app


class MockCaptchaService:
    async def verify(self, captcha_verify_param: str) -> bool:
        return True


class MockPermissionRepository:
    async def get_user_permissions(self, user_id: int) -> set[str]:
        assert user_id == 1
        return {"dashboard:view", "user:read"}

    async def get_user_roles(self, user_id: int) -> set[str]:
        assert user_id == 1
        return {"admin"}


class MockPermissionService:
    repository = MockPermissionRepository()


_engine = None


@pytest.fixture(scope="module")
def test_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


@pytest.fixture(scope="module")
def async_session_factory(test_engine):
    return sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="module")
def setup_db(test_engine):
    async def init():
        async with test_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    return init


@pytest.fixture
def db_session(setup_db, async_session_factory):
    import asyncio

    asyncio.run(setup_db())

    async def override_get_session():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_cache] = lambda: LocalCache()
    app.dependency_overrides[get_captcha_service] = lambda: MockCaptchaService()

    yield

    app.dependency_overrides.clear()


@pytest.fixture
def rbac_client(db_session):
    return TestClient(app, raise_server_exceptions=False)


def test_get_current_user_permissions_requires_auth(rbac_client):
    response = rbac_client.get("/api/v1/permissions/me")
    assert response.status_code == 401


def test_get_current_user_permissions_includes_superuser_flag(rbac_client):
    async def override_current_user():
        return User(
            id=1,
            username="devadmin",
            email="devadmin@example.com",
            hashed_password="hashed",
            is_active=True,
            is_superuser=True,
        )

    app.dependency_overrides[permissions_api.current_user] = override_current_user
    app.dependency_overrides[get_permission_service] = lambda: MockPermissionService()

    response = rbac_client.get("/api/v1/permissions/me")

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data["permissions"]) == {"dashboard:view", "user:read"}
    assert set(data["roles"]) == {"admin"}
    assert data["is_superuser"] is True
