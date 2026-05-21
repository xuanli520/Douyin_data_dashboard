from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.v1.agent_discovery as agent_discovery
from src.audit import get_audit_service
from src.api.v1.agent_discovery import _RUN_EVENTS
from src.api.v1.agent_discovery import router
from src.auth.rbac import get_permission_service
from src.domains.agent_recipe.services import get_agent_recipe_service


class _AuditService:
    async def log(self, **_kwargs):
        return None


class _PermissionService:
    async def check_permissions(self, *_args, **_kwargs):
        return True


async def _current_user():
    return type("_User", (), {"id": 1, "is_superuser": True, "is_active": True})()


def _app():
    app = FastAPI()
    app.dependency_overrides[agent_discovery.current_user] = _current_user
    app.dependency_overrides[get_permission_service] = lambda: _PermissionService()
    app.dependency_overrides[get_audit_service] = lambda: _AuditService()
    app.include_router(router, prefix="/api/v1")
    return app


def test_agent_discovery_trigger_returns_run_id(monkeypatch):
    app = _app()
    client = TestClient(app)
    pushed = []

    class _Task:
        @staticmethod
        def push(**payload):
            pushed.append(payload)

    monkeypatch.setitem(
        __import__("sys").modules,
        "src.tasks.collection.douyin_shop_discovery",
        type("_Module", (), {"run_agent_discovery": _Task})(),
    )

    response = client.post(
        "/api/v1/agent-discovery",
        json={
            "shop_id": "shop-1",
            "goal": "find value",
            "entrypoint_url": "https://example.test",
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "queued"
    assert f"agent_discovery:{body['run_id']}" in _RUN_EVENTS
    assert pushed[0]["run_id"] == body["run_id"]
    assert pushed[0]["shop_id"] == "shop-1"


def test_agent_discovery_trigger_rejects_empty_goal():
    app = _app()
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent-discovery",
        json={
            "shop_id": "shop-1",
            "goal": "",
            "entrypoint_url": "https://example.test",
        },
    )

    assert response.status_code == 422


def test_agent_discovery_trigger_requires_shop_id():
    app = _app()
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent-discovery",
        json={"goal": "find value", "entrypoint_url": "https://example.test"},
    )

    assert response.status_code == 422


def test_agent_discovery_trigger_rejects_extra_shop_selection_fields():
    app = _app()
    client = TestClient(app)

    for extra_payload in ({"shop_ids": ["shop-1"]}, {"all": True}):
        response = client.post(
            "/api/v1/agent-discovery",
            json={
                "shop_id": "shop-1",
                "goal": "find value",
                "entrypoint_url": "https://example.test",
                **extra_payload,
            },
        )

        assert response.status_code == 422


def test_agent_recipe_mark_stable_calls_service():
    app = _app()
    called = []

    class _Service:
        async def mark_stable(self, data):
            called.append(data)
            return True

    app.dependency_overrides[get_agent_recipe_service] = lambda: _Service()
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent-discovery/recipes/123/mark-stable",
        json={"expected_version": 2},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"recipe_id": 123, "status": "stable"}
    assert called[0].recipe_id == 123
    assert called[0].expected_version == 2
