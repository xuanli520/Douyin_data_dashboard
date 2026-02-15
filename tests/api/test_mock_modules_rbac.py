import pytest
from httpx import AsyncClient, ASGITransport

from src.cache import get_cache
from src.main import app
from src.auth.captcha import get_captcha_service


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
    from src.auth.models import Permission, Role, RolePermission, UserRole
    from fastapi_users.password import PasswordHelper
    from src.auth import User

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("shopuser123")

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {p.code: p for p in result.scalars().all()}

        perms_to_create = [
            ("shop:view", "查看店铺", "shop"),
            ("shop:score", "查看店铺评分", "shop"),
            ("metric:view", "查看指标", "metric"),
            ("report:view", "查看报表", "report"),
            ("schedule:view", "查看调度", "schedule"),
            ("analysis:view", "查看分析", "analysis"),
            ("alert:view", "查看预警", "alert"),
        ]

        for code, name, module in perms_to_create:
            if code not in perm_map:
                perm = Permission(code=code, name=name, module=module)
                session.add(perm)
                await session.commit()
                perm_map[code] = perm

        perm_shop_view = perm_map.get("shop:view")
        perm_shop_score = perm_map.get("shop:score")
        perm_metric_view = perm_map.get("metric:view")
        perm_report_view = perm_map.get("report:view")
        perm_schedule_view = perm_map.get("schedule:view")
        perm_analysis_view = perm_map.get("analysis:view")
        perm_alert_view = perm_map.get("alert:view")

        role_result = await session.execute(
            select(Role).where(Role.name == "shop_manager")
        )
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name="shop_manager", description="Shop Manager Role")
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

        existing_user_role = await session.execute(
            select(UserRole).where(
                UserRole.user_id == user.id, UserRole.role_id == role.id
            )
        )
        if not existing_user_role.scalar_one_or_none():
            session.add(UserRole(user_id=user.id, role_id=role.id))

        perms = [
            perm_shop_view,
            perm_shop_score,
            perm_metric_view,
            perm_report_view,
            perm_schedule_view,
            perm_analysis_view,
            perm_alert_view,
        ]
        for perm in perms:
            if perm:
                existing = await session.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm.id,
                    )
                )
                if not existing.scalar_one_or_none():
                    session.add(RolePermission(role_id=role.id, permission_id=perm.id))

        await session.commit()
        yield user


@pytest.fixture
async def superuser_data(test_db):
    from fastapi_users.password import PasswordHelper
    from src.auth import User

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("superuser123")

    async with test_db() as session:
        user = User(
            username="superuser",
            email="superuser@example.com",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user


class TestAlertsRBAC:
    @pytest.mark.asyncio
    async def test_alerts_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/alerts")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_alerts_with_permission(self, api_client, permission_data):
        headers = await get_auth_headers(
            api_client, "shopuser@example.com", "shopuser123"
        )
        response = await api_client.get("/api/v1/alerts", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_alerts_superuser_bypass(self, api_client, superuser_data):
        headers = await get_auth_headers(
            api_client, "superuser@example.com", "superuser123"
        )
        response = await api_client.get("/api/v1/alerts", headers=headers)
        assert response.status_code == 200


class TestShopsRBAC:
    @pytest.mark.asyncio
    async def test_shops_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/shops")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_shop_score_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/shops/1/score")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_shops_with_permission(self, api_client, permission_data):
        headers = await get_auth_headers(
            api_client, "shopuser@example.com", "shopuser123"
        )
        response = await api_client.get("/api/v1/shops", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_shop_score_with_permission(self, api_client, permission_data):
        headers = await get_auth_headers(
            api_client, "shopuser@example.com", "shopuser123"
        )
        response = await api_client.get("/api/v1/shops/1/score", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_shops_superuser_bypass(self, api_client, superuser_data):
        headers = await get_auth_headers(
            api_client, "superuser@example.com", "superuser123"
        )
        response = await api_client.get("/api/v1/shops", headers=headers)
        assert response.status_code == 200


class TestMetricsRBAC:
    @pytest.mark.asyncio
    async def test_metric_detail_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/metrics/product")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_metric_detail_with_permission(self, api_client, permission_data):
        headers = await get_auth_headers(
            api_client, "shopuser@example.com", "shopuser123"
        )
        response = await api_client.get("/api/v1/metrics/product", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_metric_detail_superuser_bypass(self, api_client, superuser_data):
        headers = await get_auth_headers(
            api_client, "superuser@example.com", "superuser123"
        )
        response = await api_client.get("/api/v1/metrics/product", headers=headers)
        assert response.status_code == 200


class TestReportsRBAC:
    @pytest.mark.asyncio
    async def test_reports_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/reports")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_reports_with_permission(self, api_client, permission_data):
        headers = await get_auth_headers(
            api_client, "shopuser@example.com", "shopuser123"
        )
        response = await api_client.get("/api/v1/reports", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_reports_superuser_bypass(self, api_client, superuser_data):
        headers = await get_auth_headers(
            api_client, "superuser@example.com", "superuser123"
        )
        response = await api_client.get("/api/v1/reports", headers=headers)
        assert response.status_code == 200


class TestSchedulesRBAC:
    @pytest.mark.asyncio
    async def test_schedules_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/schedules")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_schedules_with_permission(self, api_client, permission_data):
        headers = await get_auth_headers(
            api_client, "shopuser@example.com", "shopuser123"
        )
        response = await api_client.get("/api/v1/schedules", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_schedules_superuser_bypass(self, api_client, superuser_data):
        headers = await get_auth_headers(
            api_client, "superuser@example.com", "superuser123"
        )
        response = await api_client.get("/api/v1/schedules", headers=headers)
        assert response.status_code == 200


class TestAnalysisRBAC:
    @pytest.mark.asyncio
    async def test_analysis_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/analysis")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_analysis_with_permission(self, api_client, permission_data):
        headers = await get_auth_headers(
            api_client, "shopuser@example.com", "shopuser123"
        )
        response = await api_client.get("/api/v1/analysis", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_analysis_superuser_bypass(self, api_client, superuser_data):
        headers = await get_auth_headers(
            api_client, "superuser@example.com", "superuser123"
        )
        response = await api_client.get("/api/v1/analysis", headers=headers)
        assert response.status_code == 200


class TestTaskRBAC:
    @pytest.mark.asyncio
    async def test_list_tasks_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/tasks")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_task_requires_permission(self, api_client):
        response = await api_client.post("/api/v1/tasks", json={"name": "test"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_run_task_requires_permission(self, api_client):
        response = await api_client.post("/api/v1/tasks/1/run")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_task_executions_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/tasks/1/executions")
        assert response.status_code == 401
