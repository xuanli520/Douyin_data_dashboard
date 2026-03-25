from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth.captcha import get_captcha_service
from src.cache import get_cache
from src.domains.data_source.enums import DataSourceStatus, DataSourceType, TargetType
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.task.enums import TaskDefinitionStatus, TaskType
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
    app.state.task_dispatcher_registry = build_task_dispatcher_registry()

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
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
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
                name="products-active",
                task_type=TaskType.ETL_PRODUCTS,
                status=TaskDefinitionStatus.ACTIVE,
            ),
            created_by_id=permission_data.id,
        )
        await service.create_task(
            TaskDefinitionCreate(
                name="dashboard-paused",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                status=TaskDefinitionStatus.PAUSED,
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
async def test_update_task(
    api_client,
    permission_data,
    test_db,
):
    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
        task = await service.create_task(
            TaskDefinitionCreate(name="orders-task", task_type=TaskType.ETL_ORDERS),
            created_by_id=permission_data.id,
        )

    headers = await get_auth_headers(
        api_client,
        "taskmanager@example.com",
        "taskmanager123",
    )
    response = await api_client.put(
        f"/api/v1/tasks/{task.id}",
        json={
            "name": "orders-task-updated",
            "status": "PAUSED",
            "config": {"batch_date": "2026-03-16"},
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["name"] == "orders-task-updated"
    assert payload["status"] == "PAUSED"
    assert payload["config"]["batch_date"] == "2026-03-16"
    assert "schedule" not in payload


@pytest.mark.asyncio
async def test_delete_task(
    api_client,
    permission_data,
    test_db,
):
    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
        task = await service.create_task(
            TaskDefinitionCreate(name="to-delete", task_type=TaskType.ETL_PRODUCTS),
            created_by_id=permission_data.id,
        )

    headers = await get_auth_headers(
        api_client,
        "taskmanager@example.com",
        "taskmanager123",
    )
    response = await api_client.delete(f"/api/v1/tasks/{task.id}", headers=headers)
    assert response.status_code == 200

    detail = await api_client.get(f"/api/v1/tasks/{task.id}", headers=headers)
    assert detail.status_code == 404
    assert detail.json()["code"] == int(ErrorCode.TASK_NOT_FOUND)


@pytest.mark.asyncio
async def test_run_task_and_list_executions(
    api_client,
    permission_data,
    test_db,
    monkeypatch,
):
    from src.tasks import bootstrap as module

    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
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
async def test_run_shop_dashboard_task_persists_payload_and_dispatches_overrides(
    api_client,
    permission_data,
    test_db,
    monkeypatch,
):
    from src.tasks import bootstrap as module

    captured: dict[str, object] = {}
    data_source_id = 0
    rule_id = 0

    async with test_db() as session:
        data_source = DataSource(
            name="task-management-shop-data-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        session.add(data_source)
        await session.flush()
        data_source_id = data_source.id if data_source.id is not None else 0

        rule = ScrapingRule(
            name="task-management-shop-rule",
            data_source_id=data_source_id,
            target_type=TargetType.SHOP_OVERVIEW,
        )
        session.add(rule)
        await session.flush()
        rule_id = rule.id if rule.id is not None else 0

        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
        task = await service.create_task(
            TaskDefinitionCreate(
                name="shop-dashboard",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
            ),
            created_by_id=permission_data.id,
        )

    def _fake_shop_push(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(task_id="queue-shop-task-1")

    async def _skip_validate_target_shops(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        module.sync_shop_dashboard, "push", _fake_shop_push, raising=False
    )
    monkeypatch.setattr(
        TaskService,
        "_validate_shop_dashboard_target_shops",
        _skip_validate_target_shops,
    )

    headers = await get_auth_headers(
        api_client,
        "taskmanager@example.com",
        "taskmanager123",
    )

    run_resp = await api_client.post(
        f"/api/v1/tasks/{task.id}/run",
        json={
            "payload": {
                "data_source_id": data_source_id,
                "rule_id": rule_id,
                "execution_id": "shop-api-exec-1",
                "all": True,
                "shop_ids": ["shop-10", "shop-11"],
                "timezone": "Asia/Shanghai",
                "granularity": "DAY",
                "incremental_mode": "BY_DATE",
                "data_latency": "T+1",
                "filters": {"shop_id": ["shop-10", "shop-11"], "region": "east"},
                "dimensions": ["shop", "category"],
                "metrics": ["overview"],
                "top_n": 20,
                "sort_by": "-score",
                "include_long_tail": True,
                "session_level": True,
                "extra_config": {"cursor": "cursor-1"},
            }
        },
        headers=headers,
    )

    execution = assert_success_response(run_resp)

    assert execution["queue_task_id"] == "queue-shop-task-1"
    assert execution["payload"]["timezone"] == "Asia/Shanghai"
    assert execution["payload"]["filters"]["region"] == "east"
    assert captured["data_source_id"] == data_source_id
    assert captured["rule_id"] == rule_id
    assert captured["all"] is True
    assert captured["shop_ids"] == ["shop-10", "shop-11"]
    assert captured["timezone"] == "Asia/Shanghai"
    assert captured["filters"] == {"shop_id": ["shop-10", "shop-11"], "region": "east"}


@pytest.mark.asyncio
async def test_cancel_task(
    api_client,
    permission_data,
    test_db,
):
    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
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


@pytest.mark.asyncio
async def test_run_task_rejects_cancelled_task(
    api_client,
    permission_data,
    test_db,
):
    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
        task = await service.create_task(
            TaskDefinitionCreate(
                name="orders-cancelled",
                task_type=TaskType.ETL_ORDERS,
                status=TaskDefinitionStatus.CANCELLED,
            ),
            created_by_id=permission_data.id,
        )

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

    assert run_resp.status_code == 409
    payload = run_resp.json()
    assert payload["code"] == int(ErrorCode.TASK_INVALID_STATUS)


@pytest.mark.asyncio
async def test_run_shop_dashboard_task_requires_positive_ids(
    api_client,
    permission_data,
    test_db,
):
    async with test_db() as session:
        service = TaskService(
            session=session,
            dispatcher_registry=build_task_dispatcher_registry(),
        )
        task = await service.create_task(
            TaskDefinitionCreate(
                name="shop-dashboard-invalid-payload",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
            ),
            created_by_id=permission_data.id,
        )

    headers = await get_auth_headers(
        api_client,
        "taskmanager@example.com",
        "taskmanager123",
    )

    missing_rule_resp = await api_client.post(
        f"/api/v1/tasks/{task.id}/run",
        json={"payload": {"data_source_id": 10}},
        headers=headers,
    )
    assert missing_rule_resp.status_code == 400
    assert missing_rule_resp.json()["code"] == int(ErrorCode.TASK_INVALID_PAYLOAD)

    invalid_int_resp = await api_client.post(
        f"/api/v1/tasks/{task.id}/run",
        json={"payload": {"data_source_id": "abc", "rule_id": 20}},
        headers=headers,
    )
    assert invalid_int_resp.status_code == 400
    assert invalid_int_resp.json()["code"] == int(ErrorCode.TASK_INVALID_PAYLOAD)

    missing_reference_resp = await api_client.post(
        f"/api/v1/tasks/{task.id}/run",
        json={"payload": {"data_source_id": 99999, "rule_id": 99999}},
        headers=headers,
    )
    assert missing_reference_resp.status_code == 400
    assert missing_reference_resp.json()["code"] == int(ErrorCode.TASK_INVALID_PAYLOAD)
