import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth.captcha import get_captcha_service
from src.cache import get_cache
from src.domains.task.enums import TaskType
from src.domains.task.schemas import TaskDefinitionCreate, TaskExecutionCreate
from src.domains.task.services import TaskService
from src.main import app
from src.tasks.bootstrap import build_task_dispatcher_registry


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
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.pop(get_cache, None)
    app.dependency_overrides.pop(get_captcha_service, None)


async def get_auth_headers(client: AsyncClient, email: str, password: str) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password, "captchaVerifyParam": "valid"},
    )
    token = response.cookies.get("access_token")
    assert token is not None
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def permission_data(test_db):
    from fastapi_users.password import PasswordHelper

    from src.auth import User
    from src.auth.models import Permission, Role, RolePermission, UserRole

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("statususer123")

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {p.code: p for p in result.scalars().all()}

        code = "task:view"
        if code not in perm_map:
            perm = Permission(code=code, name=code, module="task")
            session.add(perm)
            await session.commit()
            perm_map[code] = perm

        role_result = await session.execute(
            select(Role).where(Role.name == "task_execution_reader")
        )
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(
                name="task_execution_reader", description="Task Execution Reader"
            )
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
        session.add(RolePermission(role_id=role.id, permission_id=perm_map[code].id))
        await session.commit()
        yield user


@pytest.mark.asyncio
async def test_task_status_endpoint_removed(api_client, permission_data):
    headers = await get_auth_headers(
        api_client,
        "statususer@example.com",
        "statususer123",
    )
    response = await api_client.get("/api/v1/task-status/task-id-1", headers=headers)
    assert response.status_code == 404
    payload = response.json()
    if "code" in payload:
        assert payload["code"] == 404
    else:
        assert payload["detail"] == "Not Found"


@pytest.mark.asyncio
async def test_task_status_read_from_task_executions(
    api_client, permission_data, test_db
):
    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
        task = await service.create_task(
            TaskDefinitionCreate(name="orders", task_type=TaskType.ETL_ORDERS),
            created_by_id=permission_data.id,
        )
        await service.create_execution(
            task,
            payload=TaskExecutionCreate(payload={"batch_date": "2026-03-08"}),
            queue_task_id="queue-status-1",
            triggered_by=permission_data.id,
        )

    headers = await get_auth_headers(
        api_client,
        "statususer@example.com",
        "statususer123",
    )
    response = await api_client.get(
        f"/api/v1/tasks/{task.id}/executions",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == task.id
    assert payload["items"]
    assert payload["items"][0]["queue_task_id"] == "queue-status-1"
