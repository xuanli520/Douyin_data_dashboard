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
    hashed_password = password_helper.hash("statususer123")

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {p.code: p for p in result.scalars().all()}

        for code in ("task:view",):
            if code not in perm_map:
                perm = Permission(code=code, name=code, module="task")
                session.add(perm)
                await session.commit()
                perm_map[code] = perm

        role_result = await session.execute(
            select(Role).where(Role.name == "task_status_viewer")
        )
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name="task_status_viewer", description="Task Status Viewer")
            session.add(role)
            await session.commit()
            await session.refresh(role)

        user = User(
            username="statususer",
            email="statususer@example.com",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        session.add(UserRole(user_id=user.id, role_id=role.id))
        session.add(
            RolePermission(role_id=role.id, permission_id=perm_map["task:view"].id)
        )
        await session.commit()
        yield user


@pytest.mark.asyncio
async def test_get_task_status_requires_permission(api_client):
    response = await api_client.get("/api/v1/task-status/task-id-1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_task_status_not_found(api_client, permission_data):
    headers = await get_auth_headers(
        api_client, "statususer@example.com", "statususer123"
    )
    response = await api_client.get("/api/v1/task-status/task-id-1", headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_task_status_success_and_audit(
    api_client, permission_data, test_db, monkeypatch
):
    from src.api.v1 import task_status as module

    class _FakeRedis:
        def hgetall(self, key):
            assert key == "douyin:task:status:task-id-2"
            return {
                "status": "SUCCESS",
                "task_name": "sync_orders",
                "triggered_by": str(permission_data.id),
            }

    monkeypatch.setattr(module, "_get_redis_client", lambda: _FakeRedis())

    headers = await get_auth_headers(
        api_client, "statususer@example.com", "statususer123"
    )
    response = await api_client.get("/api/v1/task-status/task-id-2", headers=headers)

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == "task-id-2"
    assert payload["status"]["status"] == "SUCCESS"

    async with test_db() as session:
        result = await session.execute(
            select(AuditLog)
            .where(
                AuditLog.action == AuditAction.PROTECTED_RESOURCE_ACCESS,
                AuditLog.actor_id == permission_data.id,
                AuditLog.resource_type == "task_status",
                AuditLog.resource_id == "task-id-2",
            )
            .order_by(AuditLog.id.desc())
        )
        audit_log = result.scalars().first()

    assert audit_log is not None
    assert audit_log.extra is not None
    assert audit_log.extra["status_key"] == "douyin:task:status:task-id-2"
