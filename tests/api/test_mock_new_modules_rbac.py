import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.captcha import get_captcha_service
from src.cache import get_cache
from src.main import app


class MockCaptchaService:
    async def verify(self, captcha_verify_param: str) -> bool:
        return True


@pytest.fixture
async def api_client(test_db, local_cache):
    async def override_get_cache():
        yield local_cache

    app.dependency_overrides[get_cache] = override_get_cache
    app.dependency_overrides[get_captcha_service] = lambda: MockCaptchaService()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.pop(get_cache, None)
    app.dependency_overrides.pop(get_captcha_service, None)


async def get_auth_headers(client: AsyncClient, email: str, password: str) -> dict:
    response = await client.post(
        "/api/v1/auth/jwt/login",
        data={"username": email, "password": password, "captchaVerifyParam": "valid"},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def permission_data(test_db):
    from sqlalchemy import select
    from fastapi_users.password import PasswordHelper

    from src.auth import User
    from src.auth.models import Permission, Role, RolePermission, UserRole

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("newmodule123")

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {p.code: p for p in result.scalars().all()}
        perms_to_create = [
            ("shop:view", "查看店铺", "shop"),
            ("experience:view", "查看体验分析", "experience"),
            ("metric:view", "查看指标分析", "metric"),
            ("notification:view", "查看通知渠道", "notification"),
            ("notification:test", "测试通知渠道", "notification"),
            ("export:view", "查看导出", "export"),
            ("export:create", "创建导出", "export"),
            ("export:download", "下载导出", "export"),
            ("system:config", "查看系统配置", "system"),
            ("system:health", "查看系统健康", "system"),
            ("system:backup", "系统备份", "system"),
            ("system:cleanup", "系统清理", "system"),
            ("system:user_settings", "用户设置", "system"),
        ]
        for code, name, module in perms_to_create:
            if code not in perm_map:
                perm = Permission(code=code, name=name, module=module)
                session.add(perm)
                await session.commit()
                perm_map[code] = perm

        role_result = await session.execute(
            select(Role).where(Role.name == "new_module_role")
        )
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name="new_module_role", description="new module role")
            session.add(role)
            await session.commit()
            await session.refresh(role)

        user = User(
            username="newmodule",
            email="newmodule@example.com",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        session.add(UserRole(user_id=user.id, role_id=role.id))
        for code, _, _ in perms_to_create:
            session.add(
                RolePermission(role_id=role.id, permission_id=perm_map[code].id)
            )
        await session.commit()
        yield user


@pytest.fixture
async def superuser_data(test_db):
    from fastapi_users.password import PasswordHelper

    from src.auth import User

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("supernewmodule123")

    async with test_db() as session:
        user = User(
            username="newsuperuser",
            email="newsuperuser@example.com",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user


CASES = [
    (
        "GET",
        "/api/v1/shops?shop_id=shop-1&start_date=2026-03-01&end_date=2026-03-03",
        None,
    ),
    ("GET", "/api/v1/experience/overview", None),
    ("GET", "/api/v1/experience/trend", None),
    ("GET", "/api/v1/experience/issues", None),
    ("GET", "/api/v1/experience/drilldown/product", None),
    ("GET", "/api/v1/metrics/product", None),
    ("GET", "/api/v1/notifications/channels", None),
    ("POST", "/api/v1/notifications/channels/channel_wecom/test", {}),
    ("GET", "/api/v1/exports", None),
    ("POST", "/api/v1/exports", {"name": "mock_export", "type": "orders"}),
    ("GET", "/api/v1/exports/export_1/download", None),
    ("GET", "/api/v1/system/config", None),
    ("GET", "/api/v1/system/health", None),
    ("POST", "/api/v1/system/backup", {}),
    (
        "POST",
        "/api/v1/system/cleanup",
        {"retention_days": 30, "include_exports": True},
    ),
    ("GET", "/api/v1/system/user-settings", None),
    ("PATCH", "/api/v1/system/user-settings", {"theme": "dark"}),
]


async def request_case(
    client: AsyncClient,
    method: str,
    path: str,
    payload: dict | None,
    headers: dict | None = None,
):
    if method == "GET":
        return await client.get(path, headers=headers)
    if method == "POST":
        return await client.post(path, json=payload, headers=headers)
    if method == "PATCH":
        return await client.patch(path, json=payload, headers=headers)
    raise ValueError(f"unsupported method: {method}")


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", CASES)
async def test_new_module_endpoints_require_permission(
    api_client, method, path, payload
):
    response = await request_case(api_client, method, path, payload)
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", CASES)
async def test_new_module_endpoints_with_permission(
    api_client, permission_data, method, path, payload
):
    headers = await get_auth_headers(
        api_client, "newmodule@example.com", "newmodule123"
    )
    response = await request_case(api_client, method, path, payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "data" in data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,payload",
    [
        (
            "GET",
            "/api/v1/shops?shop_id=shop-1&start_date=2026-03-01&end_date=2026-03-03",
            None,
        ),
        ("GET", "/api/v1/experience/overview", None),
        ("GET", "/api/v1/system/config", None),
    ],
)
async def test_new_module_endpoints_superuser_bypass(
    api_client, superuser_data, method, path, payload
):
    headers = await get_auth_headers(
        api_client, "newsuperuser@example.com", "supernewmodule123"
    )
    response = await request_case(api_client, method, path, payload, headers=headers)
    assert response.status_code == 200
