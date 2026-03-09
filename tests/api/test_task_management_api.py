from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth.captcha import get_captcha_service
from src.cache import get_cache
from src.domains.task.enums import TaskDefinitionStatus, TaskType
from src.domains.task.schemas import TaskDefinitionCreate
from src.domains.task.services import TaskService
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
        transport=ASGITransport(app=app),
        base_url="http://test",
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

    from src.auth import User
    from src.auth.models import Permission, Role, RolePermission, UserRole

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("taskmanager123")

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {p.code: p for p in result.scalars().all()}

        codes = {
            "task:view",
            "task:create",
            "task:execute",
            "task:cancel",
        }
        for code in codes:
            if code not in perm_map:
                perm = Permission(code=code, name=code, module="task")
                session.add(perm)
                await session.commit()
                perm_map[code] = perm

        role_result = await session.execute(
            select(Role).where(Role.name == "task_manager")
        )
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name="task_manager", description="Task Manager")
            session.add(role)
            await session.commit()
            await session.refresh(role)

        user = User(
            username="taskmanager",
            email="taskmanager@example.com",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        session.add(UserRole(user_id=user.id, role_id=role.id))
        for code in codes:
            session.add(
                RolePermission(role_id=role.id, permission_id=perm_map[code].id)
            )
        await session.commit()
        yield user


def assert_success_response(response) -> dict:
    assert response.status_code == 200
    payload = response.json()
    assert {"code", "msg", "data"} <= payload.keys()
    assert payload["code"] == 200
    assert payload["msg"] == "success"
    return payload["data"]


@pytest.mark.asyncio
async def test_list_tasks_supports_pagination_and_filters(
    api_client,
    permission_data,
    test_db,
):
    async with test_db() as session:
        service = TaskService(session)
        await service.create_task(
            TaskDefinitionCreate(
                name="orders-active",
                task_type=TaskType.ETL_ORDERS,
                status=TaskDefinitionStatus.ACTIVE,
            ),
            created_by_id=permission_data.id,
        )
        await service.create_task(
            TaskDefinitionCreate(
                name="orders-paused",
                task_type=TaskType.ETL_ORDERS,
                status=TaskDefinitionStatus.PAUSED,
            ),
            created_by_id=permission_data.id,
        )
        await service.create_task(
            TaskDefinitionCreate(
                name="products-active",
                task_type=TaskType.ETL_PRODUCTS,
                status=TaskDefinitionStatus.ACTIVE,
            ),
            created_by_id=permission_data.id,
        )

    headers = await get_auth_headers(
        api_client,
        "taskmanager@example.com",
        "taskmanager123",
    )
    response = await api_client.get(
        "/api/v1/tasks?page=1&size=10&status=ACTIVE&task_type=ETL_ORDERS",
        headers=headers,
    )

    data = assert_success_response(response)
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "orders-active"
    assert data["meta"]["page"] == 1
    assert data["meta"]["size"] == 10
    assert data["meta"]["total"] == 1


@pytest.mark.asyncio
async def test_create_and_get_task_detail(
    api_client,
    permission_data,
):
    headers = await get_auth_headers(
        api_client,
        "taskmanager@example.com",
        "taskmanager123",
    )

    create_resp = await api_client.post(
        "/api/v1/tasks",
        json={
            "name": "orders-task",
            "task_type": "ETL_ORDERS",
            "config": {"batch_date": "2026-03-08"},
        },
        headers=headers,
    )
    created = assert_success_response(create_resp)

    detail_resp = await api_client.get(
        f"/api/v1/tasks/{created['id']}",
        headers=headers,
    )
    detail = assert_success_response(detail_resp)

    assert detail["id"] == created["id"]
    assert detail["task_type"] == "ETL_ORDERS"
    assert detail["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_run_task_and_list_executions(
    api_client,
    permission_data,
    test_db,
    monkeypatch,
):
    from src.domains.task import services as module

    async with test_db() as session:
        service = TaskService(session)
        task = await service.create_task(
            TaskDefinitionCreate(name="orders", task_type=TaskType.ETL_ORDERS),
            created_by_id=permission_data.id,
        )

    def _fake_push(**kwargs):
        assert kwargs["batch_date"] == "2026-03-08"
        assert kwargs["triggered_by"] == permission_data.id
        return SimpleNamespace(task_id="queue-task-1")

    monkeypatch.setattr(module.process_orders, "push", _fake_push, raising=False)

    headers = await get_auth_headers(
        api_client,
        "taskmanager@example.com",
        "taskmanager123",
    )

    run_resp = await api_client.post(
        f"/api/v1/tasks/{task.id}/run",
        json={"payload": {"batch_date": "2026-03-08"}},
        headers=headers,
    )
    execution = assert_success_response(run_resp)
    assert execution["task_id"] == task.id
    assert execution["queue_task_id"] == "queue-task-1"
    assert execution["status"] == "QUEUED"

    executions_resp = await api_client.get(
        f"/api/v1/tasks/{task.id}/executions",
        headers=headers,
    )
    executions = assert_success_response(executions_resp)
    assert executions["task_id"] == task.id
    assert executions["items"]
    assert executions["items"][0]["queue_task_id"] == "queue-task-1"


@pytest.mark.asyncio
async def test_cancel_task(
    api_client,
    permission_data,
    test_db,
):
    async with test_db() as session:
        service = TaskService(session)
        task = await service.create_task(
            TaskDefinitionCreate(name="products", task_type=TaskType.ETL_PRODUCTS),
            created_by_id=permission_data.id,
        )

    headers = await get_auth_headers(
        api_client,
        "taskmanager@example.com",
        "taskmanager123",
    )

    cancel_resp = await api_client.post(
        f"/api/v1/tasks/{task.id}/cancel",
        headers=headers,
    )
    cancelled = assert_success_response(cancel_resp)
    assert cancelled["id"] == task.id
    assert cancelled["status"] == "CANCELLED"
