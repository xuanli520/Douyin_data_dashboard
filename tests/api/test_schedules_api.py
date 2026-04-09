from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth.captcha import get_captcha_service
from src.cache import get_cache
from src.domains.collection_job.schemas import CollectionJobCreate
from src.domains.collection_job.services import CollectionJobService
from src.domains.data_source.enums import DataSourceStatus, DataSourceType, TargetType
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.task.enums import TaskType
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
    hashed_password = password_helper.hash("schedulemanager123")

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {p.code: p for p in result.scalars().all()}

        codes = {
            "schedule:view",
            "schedule:update",
            "schedule:delete",
        }
        for code in codes:
            if code not in perm_map:
                perm = Permission(code=code, name=code, module="schedule")
                session.add(perm)
                await session.commit()
                perm_map[code] = perm

        role_result = await session.execute(
            select(Role).where(Role.name == "schedule_manager")
        )
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name="schedule_manager", description="Schedule Manager")
            session.add(role)
            await session.commit()
            await session.refresh(role)

        user = User(
            username="schedulemanager",
            email="schedulemanager@example.com",
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

        data_source = DataSource(
            name="schedule-api-data-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        session.add(data_source)
        await session.flush()

        data_source_id = data_source.id if data_source.id is not None else 0
        rule = ScrapingRule(
            name="schedule-api-rule",
            data_source_id=data_source_id,
            target_type=TargetType.SHOP_OVERVIEW,
        )
        session.add(rule)
        await session.flush()
        rule_id = rule.id if rule.id is not None else 0

        await session.commit()
        yield SimpleNamespace(
            id=user.id,
            data_source_id=data_source_id,
            rule_id=rule_id,
        )


@pytest.mark.asyncio
async def test_update_schedule(
    api_client,
    permission_data,
    test_db,
):
    async with test_db() as session:
        service = CollectionJobService(session=session)
        job = await service.create(
            CollectionJobCreate(
                name="daily-gmv",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=permission_data.data_source_id,
                rule_id=permission_data.rule_id,
                schedule={"cron": "0 9 * * *", "timezone": "Asia/Shanghai"},
            )
        )

    headers = await get_auth_headers(
        api_client,
        "schedulemanager@example.com",
        "schedulemanager123",
    )
    response = await api_client.put(
        f"/api/v1/schedules/{job.id}",
        json={
            "name": "daily-gmv-updated",
            "status": "INACTIVE",
            "schedule": {
                "cron": "0 */6 * * *",
                "timezone": "Asia/Shanghai",
                "kwargs": {"batch_date": "2026-03-16"},
            },
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["name"] == "daily-gmv-updated"
    assert payload["status"] == "INACTIVE"
    assert payload["schedule"]["cron"] == "0 */6 * * *"


@pytest.mark.asyncio
async def test_delete_schedule(
    api_client,
    permission_data,
    test_db,
):
    async with test_db() as session:
        service = CollectionJobService(session=session)
        job = await service.create(
            CollectionJobCreate(
                name="to-delete",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=permission_data.data_source_id,
                rule_id=permission_data.rule_id,
                schedule={"cron": "0 10 * * *", "timezone": "Asia/Shanghai"},
            )
        )

    headers = await get_auth_headers(
        api_client,
        "schedulemanager@example.com",
        "schedulemanager123",
    )
    response = await api_client.delete(
        f"/api/v1/schedules/{job.id}",
        headers=headers,
    )

    assert response.status_code == 200
    detail = await api_client.put(
        f"/api/v1/schedules/{job.id}",
        json={"name": "after-delete"},
        headers=headers,
    )
    assert detail.status_code == 404
