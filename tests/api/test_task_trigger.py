import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from src.main import app
from src.session import get_session
from src.cache import LocalCache, get_cache
from src.auth.captcha import get_captcha_service
from src.auth.permissions import TaskPermission


class MockCaptchaService:
    async def verify(self, captcha_verify_param: str) -> bool:
        return True


_engine = None


@pytest.fixture(scope="module")
def test_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


@pytest.fixture(scope="module")
def async_session_factory(test_engine):
    return sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="module")
def setup_db(test_engine):
    async def init():
        async with test_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    return init


@pytest.fixture
def db_session(setup_db, async_session_factory):
    import asyncio

    asyncio.run(setup_db())

    async def override_get_session():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_cache] = lambda: LocalCache()
    app.dependency_overrides[get_captcha_service] = lambda: MockCaptchaService()

    yield

    app.dependency_overrides.clear()


@pytest.fixture
def client(db_session):
    return TestClient(app, raise_server_exceptions=False)


class TestTaskAPIPermissions:
    def test_list_tasks_requires_authentication(self, client):
        response = client.get("/api/v1/tasks")
        assert response.status_code == 401

    def test_create_task_requires_authentication(self, client):
        response = client.post("/api/v1/tasks", json={"name": "test"})
        assert response.status_code == 401

    def test_run_task_requires_authentication(self, client):
        response = client.post("/api/v1/tasks/1/run")
        assert response.status_code == 401

    def test_get_task_executions_requires_authentication(self, client):
        response = client.get("/api/v1/tasks/1/executions")
        assert response.status_code == 401


class TestTaskPermissionEnum:
    def test_task_permission_view_exists(self):
        assert TaskPermission.VIEW == "task:view"

    def test_task_permission_create_exists(self):
        assert TaskPermission.CREATE == "task:create"

    def test_task_permission_execute_exists(self):
        assert TaskPermission.EXECUTE == "task:execute"

    def test_task_permission_cancel_exists(self):
        assert TaskPermission.CANCEL == "task:cancel"


class TestTaskTriggerContext:
    @patch("src.tasks.base.logger")
    def test_triggered_by_passed_in_task_kwargs(self, mock_logger):
        mock_task = MagicMock()
        mock_task.name = "sync_orders"
        mock_task.request = MagicMock()
        mock_task.request.id = "test-id"
        mock_task.request.delivery_info = {"routing_key": "default"}

        user_id = 123
        kwargs = {"shop_id": "shop_abc", "triggered_by": user_id}

        from src.tasks.base import BaseTask

        BaseTask.before_start(mock_task, "test-id", (), kwargs)

        mock_task._safe_update_status.assert_called()
        call_kwargs = mock_task._safe_update_status.call_args
        status_data = call_kwargs[0][2]

        assert status_data["triggered_by"] == user_id

    @patch("src.tasks.base.logger")
    def test_triggered_by_none_when_not_provided(self, mock_logger):
        from src.tasks.base import BaseTask

        mock_task = MagicMock()
        mock_task.name = "test_task"
        mock_task.request = MagicMock()
        mock_task.request.id = "test-id"
        mock_task.request.delivery_info = {}

        kwargs = {"shop_id": "shop_abc"}

        BaseTask.before_start(mock_task, "test-id", (), kwargs)

        mock_task._safe_update_status.assert_called()
        call_kwargs = mock_task._safe_update_status.call_args
        status_data = call_kwargs[0][2]

        assert status_data["triggered_by"] is None
