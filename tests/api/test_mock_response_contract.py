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
async def contract_user(test_db):
    from sqlalchemy import select
    from fastapi_users.password import PasswordHelper

    from src.auth import User
    from src.auth.models import Permission, Role, RolePermission, UserRole

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("contract123")
    permission_codes = [
        "shop:view",
        "shop:score",
        "metric:view",
        "experience:view",
        "dashboard:view",
        "order:view",
        "product:view",
        "sale:view",
        "after_sale:view",
        "alert:view",
        "alert:assign",
        "alert:resolve",
        "alert:ignore",
        "alert:rule",
        "alert:acknowledge",
        "task:view",
        "task:create",
        "task:execute",
        "report:view",
        "report:generate",
        "report:download",
        "export:view",
        "export:create",
        "export:download",
        "notification:view",
        "notification:test",
        "system:config",
        "system:health",
        "system:backup",
        "system:cleanup",
        "system:user_settings",
    ]

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {perm.code: perm for perm in result.scalars().all()}
        for code in permission_codes:
            if code not in perm_map:
                module = code.split(":", 1)[0]
                permission = Permission(code=code, name=code, module=module)
                session.add(permission)
                await session.commit()
                perm_map[code] = permission
        role = Role(name="contract_role", description="contract role")
        session.add(role)
        await session.commit()
        await session.refresh(role)

        user = User(
            username="contractuser",
            email="contractuser@example.com",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        session.add(UserRole(user_id=user.id, role_id=role.id))
        for code in permission_codes:
            permission = perm_map.get(code)
            if permission:
                session.add(
                    RolePermission(role_id=role.id, permission_id=permission.id)
                )
        await session.commit()
        yield user


def assert_contract(payload: dict):
    assert {"code", "msg", "data"} <= payload.keys()
    assert {"mock", "expected_release", "data"} <= payload["data"].keys()
    assert isinstance(payload["data"]["mock"], bool)
    assert payload["data"]["expected_release"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/shops?page=1&size=5",
        "/api/v1/orders/trend",
        "/api/v1/products/ranking",
        "/api/v1/sales/by-channel",
        "/api/v1/after-sales/refund-rate",
        "/api/v1/alerts?page=1&size=5",
        "/api/v1/reports?page=1&size=5",
        "/api/v1/exports?page=1&size=5",
        "/api/v1/system/config",
    ],
)
async def test_mock_response_contract(api_client, contract_user, path):
    headers = await get_auth_headers(
        api_client, "contractuser@example.com", "contract123"
    )
    response = await api_client.get(path, headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert_contract(payload)


@pytest.mark.asyncio
async def test_paginated_contract_meta(api_client, contract_user):
    headers = await get_auth_headers(
        api_client, "contractuser@example.com", "contract123"
    )
    response = await api_client.get("/api/v1/reports?page=2&size=3", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]["data"]
    assert {"items", "meta"} <= data.keys()
    assert {"page", "size", "total", "pages", "has_next", "has_prev"} <= data[
        "meta"
    ].keys()
    assert data["meta"]["page"] == 2
    assert data["meta"]["size"] == 3


@pytest.mark.asyncio
async def test_alert_enum_values(api_client, contract_user):
    headers = await get_auth_headers(
        api_client, "contractuser@example.com", "contract123"
    )
    alerts = await api_client.get("/api/v1/alerts?page=1&size=10", headers=headers)
    assert alerts.status_code == 200
    alert_statuses = {item["status"] for item in alerts.json()["data"]["data"]["items"]}
    assert alert_statuses <= {"pending", "processing", "resolved", "ignored"}
