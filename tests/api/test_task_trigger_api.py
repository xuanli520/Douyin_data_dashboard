import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.audit.schemas import AuditAction, AuditLog
from src.auth.captcha import get_captcha_service
from src.cache import get_cache
from src.domains.task.enums import TaskType
from src.domains.task.schemas import TaskDefinitionCreate
from src.domains.task.services import TaskService
from src.main import app
from src.shared.errors import ErrorCode
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

        for code in ("task:view", "task:execute", "task:create"):
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
        for code in ("task:view", "task:execute", "task:create"):
            session.add(
                RolePermission(role_id=role.id, permission_id=perm_map[code].id)
            )
        await session.commit()
        yield user


@pytest.fixture
async def no_execute_permission_data(test_db):
    from fastapi_users.password import PasswordHelper
    from sqlalchemy import select

    from src.auth import User
    from src.auth.models import Permission, Role, RolePermission, UserRole

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("readonly123")

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {p.code: p for p in result.scalars().all()}

        if "task:view" not in perm_map:
            perm = Permission(code="task:view", name="task:view", module="task")
            session.add(perm)
            await session.commit()
            perm_map["task:view"] = perm

        role_result = await session.execute(
            select(Role).where(Role.name == "task_viewer")
        )
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name="task_viewer", description="Task Viewer")
            session.add(role)
            await session.commit()
            await session.refresh(role)

        user = User(
            username="readonly",
            email="readonly@example.com",
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
async def test_create_task_requires_permission(api_client):
    response = await api_client.post(
        "/api/v1/tasks",
        json={"name": "orders", "task_type": "ETL_ORDERS"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_run_task_forbidden_without_execute_permission(
    api_client, no_execute_permission_data, test_db
):
    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
        task = await service.create_task(
            TaskDefinitionCreate(name="orders", task_type=TaskType.ETL_ORDERS),
            created_by_id=no_execute_permission_data.id,
        )

    headers = await get_auth_headers(api_client, "readonly@example.com", "readonly123")
    response = await api_client.post(
        f"/api/v1/tasks/{task.id}/run",
        json={"payload": {"batch_date": "2026-03-03"}},
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_task_executions_requires_permission(api_client):
    response = await api_client.get("/api/v1/tasks/1/executions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_task_with_permission(api_client, permission_data):
    headers = await get_auth_headers(api_client, "shopuser@example.com", "shopuser123")
    response = await api_client.post(
        "/api/v1/tasks",
        json={
            "name": "orders-task",
            "task_type": "ETL_ORDERS",
            "config": {"batch_date": "2026-03-03"},
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert {"code", "msg", "data"} <= payload.keys()
    assert payload["data"]["task_type"] == "ETL_ORDERS"
    assert payload["data"]["id"] > 0


@pytest.mark.asyncio
async def test_run_task_push_and_audit(
    api_client, permission_data, test_db, monkeypatch
):
    from types import SimpleNamespace

    from src.tasks import bootstrap as task_service_module

    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
        task = await service.create_task(
            TaskDefinitionCreate(name="orders", task_type=TaskType.ETL_ORDERS),
            created_by_id=permission_data.id,
        )

    pushed_kwargs = {}

    def _fake_push(**kwargs):
        pushed_kwargs.update(kwargs)
        return SimpleNamespace(task_id="queue-task-1")

    monkeypatch.setattr(
        task_service_module.process_orders, "push", _fake_push, raising=False
    )

    headers = await get_auth_headers(api_client, "shopuser@example.com", "shopuser123")
    response = await api_client.post(
        f"/api/v1/tasks/{task.id}/run",
        json={"payload": {"batch_date": "2026-03-03"}},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == task.id
    assert payload["queue_task_id"] == "queue-task-1"
    assert payload["triggered_by"] == permission_data.id
    assert payload["status"] == "QUEUED"
    assert pushed_kwargs["batch_date"] == "2026-03-03"
    assert pushed_kwargs["triggered_by"] == permission_data.id
    assert int(pushed_kwargs["execution_id"]) > 0

    async with test_db() as session:
        result = await session.execute(
            select(AuditLog)
            .where(
                AuditLog.action == AuditAction.TASK_RUN,
                AuditLog.actor_id == permission_data.id,
                AuditLog.resource_id == str(task.id),
            )
            .order_by(AuditLog.id.desc())
        )
        audit_log = result.scalars().first()

    assert audit_log is not None
    assert audit_log.resource_type == "task"
    assert audit_log.extra is not None
    assert audit_log.extra["queue_task_id"] == "queue-task-1"


@pytest.mark.asyncio
async def test_create_task_with_invalid_task_type_returns_validation_error(
    api_client, permission_data
):
    headers = await get_auth_headers(api_client, "shopuser@example.com", "shopuser123")
    response = await api_client.post(
        "/api/v1/tasks",
        json={"name": "shop-9", "task_type": "INVALID_TASK_TYPE"},
        headers=headers,
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == 422


@pytest.mark.asyncio
async def test_run_task_uses_task_type_dispatch(
    api_client, permission_data, test_db, monkeypatch
):
    from types import SimpleNamespace

    from src.tasks import bootstrap as task_service_module

    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
        task = await service.create_task(
            TaskDefinitionCreate(name="products", task_type=TaskType.ETL_PRODUCTS),
            created_by_id=permission_data.id,
        )

    calls = []

    def _fake_products_push(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(task_id="queue-products-1")

    monkeypatch.setattr(
        task_service_module.process_products, "push", _fake_products_push, raising=False
    )

    headers = await get_auth_headers(api_client, "shopuser@example.com", "shopuser123")
    response = await api_client.post(
        f"/api/v1/tasks/{task.id}/run",
        json={"payload": {"batch_date": "2026-03-03"}},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["queue_task_id"] == "queue-products-1"
    assert calls and calls[0]["batch_date"] == "2026-03-03"


@pytest.mark.asyncio
async def test_run_task_missing_queue_task_id_returns_business_error(
    api_client, permission_data, test_db, monkeypatch
):
    from src.tasks import bootstrap as task_service_module

    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
        task = await service.create_task(
            TaskDefinitionCreate(name="orders", task_type=TaskType.ETL_ORDERS),
            created_by_id=permission_data.id,
        )

    def _fake_push_without_task_id(**_kwargs):
        return object()

    monkeypatch.setattr(
        task_service_module.process_orders,
        "push",
        _fake_push_without_task_id,
        raising=False,
    )

    headers = await get_auth_headers(api_client, "shopuser@example.com", "shopuser123")
    response = await api_client.post(
        f"/api/v1/tasks/{task.id}/run",
        json={"payload": {"batch_date": "2026-03-03"}},
        headers=headers,
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == int(ErrorCode.TASK_PUSH_FAILED)
