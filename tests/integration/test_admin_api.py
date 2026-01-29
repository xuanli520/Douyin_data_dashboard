import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.session import get_session
from src.auth.models import User, Role, Permission, UserRole, RolePermission
from src.auth.backend import get_password_hash

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def async_engine():
    from sqlmodel import SQLModel

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_session(async_engine):
    async_session_factory = sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_factory() as session:
        yield session


@pytest.fixture
async def admin_user(test_session):
    """Create test superadmin user"""
    role = Role(name="admin", is_system=True)
    test_session.add(role)
    await test_session.commit()
    await test_session.refresh(role)

    user = User(
        username="admin",
        email="admin@test.com",
        hashed_password=get_password_hash("admin123"),
        is_active=True,
        is_superuser=True,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)

    user_role = UserRole(user_id=user.id, role_id=role.id)
    test_session.add(user_role)

    permissions = [
        Permission(
            code="user:read",
            name="查看用户",
            module="user",
            description="查看用户列表和详情",
        ),
        Permission(
            code="user:create", name="创建用户", module="user", description="创建新用户"
        ),
        Permission(
            code="user:update",
            name="更新用户",
            module="user",
            description="更新用户信息",
        ),
        Permission(
            code="user:delete", name="删除用户", module="user", description="删除用户"
        ),
        Permission(
            code="user:manage_roles",
            name="管理用户角色",
            module="user",
            description="分配/移除用户角色",
        ),
        Permission(
            code="role:read",
            name="查看角色",
            module="role",
            description="查看角色列表和详情",
        ),
        Permission(
            code="role:create", name="创建角色", module="role", description="创建新角色"
        ),
        Permission(
            code="role:update",
            name="更新角色",
            module="role",
            description="更新角色信息",
        ),
        Permission(
            code="role:delete", name="删除角色", module="role", description="删除角色"
        ),
        Permission(
            code="role:manage_permissions",
            name="管理角色权限",
            module="role",
            description="分配/移除角色权限",
        ),
        Permission(
            code="permission:read",
            name="查看权限",
            module="permission",
            description="查看权限列表",
        ),
        Permission(
            code="system:settings",
            name="系统设置",
            module="system",
            description="系统设置",
        ),
        Permission(
            code="system:logs",
            name="查看日志",
            module="system",
            description="查看系统日志",
        ),
    ]
    for perm in permissions:
        test_session.add(perm)
    await test_session.commit()

    role_permissions = [
        RolePermission(role_id=role.id, permission_id=perm.id) for perm in permissions
    ]
    for rp in role_permissions:
        test_session.add(rp)
    await test_session.commit()

    return user


@pytest.fixture
async def admin_token(async_engine, admin_user):
    """Generate admin token"""
    from src.auth.backend import get_jwt_strategy
    from src.config import get_settings

    settings = get_settings()
    strategy = get_jwt_strategy(settings)
    token = await strategy.write_token(admin_user)
    return token


@pytest.fixture
async def test_client(async_engine, test_session, admin_token):
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
    )
    from src.cache import close_cache, get_cache
    from src.config import get_settings
    from src.handlers import register_exception_handlers
    from src.middleware.cors import get_cors_middleware
    from src.middleware.monitor import MonitorMiddleware
    from src.middleware.rate_limit import RateLimitMiddleware
    from src.responses.middleware import ResponseWrapperMiddleware
    from src.session import close_db

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

    add_pagination(app)

    async_session_factory = sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_session():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    async def override_get_cache():
        from src.cache import LocalCache

        cache = LocalCache()
        yield cache

    app.dependency_overrides[get_cache] = override_get_cache

    from src.auth.captcha import get_captcha_service

    class MockCaptchaService:
        async def verify(self, captcha_verify_param: str) -> bool:
            return True

    app.dependency_overrides[get_captcha_service] = lambda: MockCaptchaService()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {admin_token}"
        yield client


class TestAdminUsersAPI:
    async def test_list_users_success(self, test_client):
        """Test getting user list"""
        response = await test_client.get("/api/admin/users")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "items" in data["data"]
        assert "total" in data["data"]

    async def test_list_users_with_filters(self, test_client):
        """Test user list with filters"""
        response = await test_client.get(
            "/api/admin/users?is_active=true&username=admin"
        )
        assert response.status_code == 200

    async def test_get_user_detail(self, test_client, admin_user):
        """Test getting user detail"""
        response = await test_client.get(f"/api/admin/users/{admin_user.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["username"] == "admin"

    async def test_create_user(self, test_client):
        """Test creating user"""
        response = await test_client.post(
            "/api/admin/users",
            json={
                "username": "newuser",
                "email": "newuser@test.com",
                "password": "password123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["username"] == "newuser"
        assert data["data"]["email"] == "newuser@test.com"

    async def test_update_user(self, test_client, admin_user):
        """Test updating user"""
        response = await test_client.patch(
            f"/api/admin/users/{admin_user.id}",
            json={
                "department": "Engineering",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["department"] == "Engineering"

    async def test_delete_user(self, test_client):
        """Test deleting user"""
        create_resp = await test_client.post(
            "/api/admin/users",
            json={
                "username": "todelete",
                "email": "todelete@test.com",
                "password": "password123",
            },
        )
        user_id = create_resp.json()["data"]["id"]

        del_resp = await test_client.delete(f"/api/admin/users/{user_id}")
        assert del_resp.status_code == 200

        get_resp = await test_client.get(f"/api/admin/users/{user_id}")
        assert get_resp.status_code == 404


class TestAdminRolesAPI:
    async def test_list_roles(self, test_client):
        """Test getting role list"""
        response = await test_client.get("/api/admin/roles")
        assert response.status_code == 200

    async def test_create_role(self, test_client):
        """Test creating role"""
        response = await test_client.post(
            "/api/admin/roles",
            json={
                "name": "test_role",
                "description": "Test role",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "test_role"


class TestAdminPermissionsAPI:
    async def test_list_permissions(self, test_client):
        """Test getting permission list"""
        response = await test_client.get("/api/admin/permissions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) > 0


class TestUserSearch:
    async def test_search_by_username(self, test_client):
        """Test searching by username"""
        response = await test_client.get("/api/admin/users?username=admin")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total"] >= 1

    async def test_filter_by_status(self, test_client):
        """Test filtering by status"""
        response = await test_client.get("/api/admin/users?is_active=true")
        assert response.status_code == 200

    async def test_pagination(self, test_client):
        """Test pagination"""
        response = await test_client.get("/api/admin/users?page=1&size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]["items"]) <= 10
