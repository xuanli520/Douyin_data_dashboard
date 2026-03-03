import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth.captcha import get_captcha_service
from src.audit.schemas import AuditAction, AuditLog
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
    from fastapi_users.password import PasswordHelper
    from sqlalchemy import select

    from src.auth import User
    from src.auth.models import Permission, Role, RolePermission, UserRole

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("shopuser123")

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {p.code: p for p in result.scalars().all()}

        for code in ("task:view", "task:execute"):
            if code not in perm_map:
                perm = Permission(code=code, name=code, module="task")
                session.add(perm)
                await session.commit()
                perm_map[code] = perm

        role_result = await session.execute(
            select(Role).where(Role.name == "task_operator")
        )
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name="task_operator", description="Task Operator")
            session.add(role)
            await session.commit()
            await session.refresh(role)

        user = User(
            username="shopuser",
            email="shopuser@example.com",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        session.add(UserRole(user_id=user.id, role_id=role.id))
        for code in ("task:view", "task:execute"):
            session.add(
                RolePermission(role_id=role.id, permission_id=perm_map[code].id)
            )
        await session.commit()
        yield user


@pytest.mark.asyncio
async def test_collection_orders_trigger_requires_permission(api_client):
    response = await api_client.post(
        "/api/v1/tasks/collection/orders/trigger",
        json={"shop_id": "shop-1", "date": "2026-03-03"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_task_status_requires_permission(api_client):
    response = await api_client.get("/api/v1/task-status/task-id-1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_collection_orders_trigger_with_permission(api_client, permission_data):
    headers = await get_auth_headers(api_client, "shopuser@example.com", "shopuser123")
    response = await api_client.post(
        "/api/v1/tasks/collection/orders/trigger",
        json={"shop_id": "shop-1", "date": "2026-03-03"},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert {"code", "msg", "data"} <= payload.keys()
    assert "task_id" in payload["data"]


@pytest.mark.asyncio
async def test_collection_orders_trigger_push_and_audit(
    api_client, permission_data, test_db, monkeypatch
):
    from types import SimpleNamespace

    from src.api.v1 import task as task_module

    pushed_kwargs = {}

    def _fake_push(**kwargs):
        pushed_kwargs.update(kwargs)
        return SimpleNamespace(task_id="task-trigger-1")

    monkeypatch.setattr(task_module.sync_orders, "push", _fake_push, raising=False)

    headers = await get_auth_headers(api_client, "shopuser@example.com", "shopuser123")
    response = await api_client.post(
        "/api/v1/tasks/collection/orders/trigger",
        json={"shop_id": "shop-1", "date": "2026-03-03"},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == "task-trigger-1"
    assert payload["queue_name"] == "collection_orders"
    assert payload["triggered_by"] == permission_data.id
    assert pushed_kwargs == {
        "shop_id": "shop-1",
        "date": "2026-03-03",
        "triggered_by": permission_data.id,
    }

    async with test_db() as session:
        result = await session.execute(
            select(AuditLog)
            .where(
                AuditLog.action == AuditAction.TASK_RUN,
                AuditLog.actor_id == permission_data.id,
                AuditLog.resource_id == "task-trigger-1",
            )
            .order_by(AuditLog.id.desc())
        )
        audit_log = result.scalars().first()

    assert audit_log is not None
    assert audit_log.resource_type == "task"
    assert audit_log.extra is not None
    assert audit_log.extra["queue_name"] == "collection_orders"
    assert audit_log.extra["payload"]["shop_id"] == "shop-1"
