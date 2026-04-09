from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.audit.schemas import AuditAction, AuditLog
from src.auth.captcha import get_captcha_service
from src.cache import get_cache
from src.domains.task.enums import TaskDefinitionStatus, TaskType
from src.domains.task.events import TaskExecutionTriggeredEvent, TaskStatusChangedEvent
from src.domains.task.schemas import TaskDefinitionCreate
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
    hashed_password = password_helper.hash("taskaudit123")

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {p.code: p for p in result.scalars().all()}

        codes = {
            "task:view",
            "task:create",
            "task:update",
            "task:delete",
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
            select(Role).where(Role.name == "task_auditor")
        )
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name="task_auditor", description="Task Auditor")
            session.add(role)
            await session.commit()
            await session.refresh(role)

        user = User(
            username="taskauditor",
            email="taskauditor@example.com",
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


@pytest.mark.asyncio
async def test_task_management_api_writes_audit_logs(
    api_client,
    permission_data,
    test_db,
    monkeypatch,
):
    from src.tasks import bootstrap as task_services

    def _fake_push(**_kwargs):
        return SimpleNamespace(task_id="audit-queue-task")

    monkeypatch.setattr(task_services.process_orders, "push", _fake_push, raising=False)

    headers = await get_auth_headers(
        api_client,
        "taskauditor@example.com",
        "taskaudit123",
    )

    create_resp = await api_client.post(
        "/api/v1/tasks",
        json={
            "name": "audit-orders",
            "task_type": "ETL_ORDERS",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["data"]["id"]

    run_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/run",
        json={"payload": {"batch_date": "2026-03-08"}},
        headers=headers,
    )
    assert run_resp.status_code == 200

    cancel_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        headers=headers,
    )
    assert cancel_resp.status_code == 200

    update_resp = await api_client.put(
        f"/api/v1/tasks/{task_id}",
        json={"name": "audit-orders-updated", "status": "PAUSED"},
        headers=headers,
    )
    assert update_resp.status_code == 200

    delete_resp = await api_client.delete(
        f"/api/v1/tasks/{task_id}",
        headers=headers,
    )
    assert delete_resp.status_code == 200

    async with test_db() as session:
        result = await session.execute(
            select(AuditLog)
            .where(
                AuditLog.actor_id == permission_data.id,
                AuditLog.action.in_(
                    [
                        AuditAction.TASK_CREATE,
                        AuditAction.TASK_RUN,
                        AuditAction.TASK_STOP,
                        AuditAction.TASK_UPDATE,
                        AuditAction.DELETE,
                    ]
                ),
                AuditLog.resource_type == "task",
                AuditLog.resource_id == str(task_id),
            )
            .order_by(AuditLog.id.asc())
        )
        logs = result.scalars().all()

    actions = [log.action for log in logs]
    assert AuditAction.TASK_CREATE in actions
    assert AuditAction.TASK_RUN in actions
    assert AuditAction.TASK_STOP in actions
    assert AuditAction.TASK_UPDATE in actions
    assert AuditAction.DELETE in actions


@pytest.mark.asyncio
async def test_task_service_emits_domain_events(test_db, monkeypatch):
    from src.tasks import bootstrap as task_services

    def _fake_push(**_kwargs):
        return SimpleNamespace(task_id="event-queue-task")

    monkeypatch.setattr(task_services.process_orders, "push", _fake_push, raising=False)

    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
        task = await service.create_task(
            TaskDefinitionCreate(
                name="event-orders",
                task_type=TaskType.ETL_ORDERS,
                status=TaskDefinitionStatus.ACTIVE,
            ),
            created_by_id=1,
        )

        execution = await service.run_task(
            task_id=task.id if task.id is not None else 0,
            payload={"batch_date": "2026-03-08"},
            triggered_by=1,
        )
        run_events = service.pull_events()

        cancelled = await service.cancel_task(task, changed_by_id=1)
        cancel_events = service.pull_events()

    execution_events = [
        event for event in run_events if isinstance(event, TaskExecutionTriggeredEvent)
    ]
    status_events = [
        event for event in cancel_events if isinstance(event, TaskStatusChangedEvent)
    ]

    assert execution_events
    assert execution_events[0].execution_id == execution.id
    assert execution_events[0].queue_task_id == "event-queue-task"

    assert status_events
    assert status_events[0].task_id == cancelled.id
    assert status_events[0].old_status == TaskDefinitionStatus.ACTIVE
    assert status_events[0].new_status == TaskDefinitionStatus.CANCELLED
