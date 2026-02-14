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


class TestAlertsRBAC:
    @pytest.mark.asyncio
    async def test_alerts_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/alerts")
        assert response.status_code == 401


class TestShopsRBAC:
    @pytest.mark.asyncio
    async def test_shops_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/shops")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_shop_score_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/shops/1/score")
        assert response.status_code == 401


class TestMetricsRBAC:
    @pytest.mark.asyncio
    async def test_metric_detail_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/metrics/product")
        assert response.status_code == 401


class TestReportsRBAC:
    @pytest.mark.asyncio
    async def test_reports_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/reports")
        assert response.status_code == 401


class TestSchedulesRBAC:
    @pytest.mark.asyncio
    async def test_schedules_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/schedules")
        assert response.status_code == 401


class TestAnalysisRBAC:
    @pytest.mark.asyncio
    async def test_analysis_requires_permission(self, api_client):
        response = await api_client.get("/api/v1/analysis")
        assert response.status_code == 401


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
