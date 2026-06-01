from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.v1.agent_login as agent_login
from src.api.v1.agent_login import _RUN_EVENTS
from src.api.v1.agent_login import append_login_event
from src.api.v1.agent_login import router
from src.audit import get_audit_service
from src.auth.rbac import get_permission_service


class _AuditService:
    async def log(self, **_kwargs):
        return None


class _PermissionService:
    async def check_permissions(self, *_args, **_kwargs):
        return True


class _FakeRedis:
    def __init__(self):
        self.values = []
        self.expired = []

    def rpush(self, key, value):
        self.values.append((key, value))

    def expire(self, key, ttl):
        self.expired.append((key, ttl))


async def _current_user():
    return type("_User", (), {"id": 1, "is_superuser": True, "is_active": True})()


def _app():
    app = FastAPI()
    app.dependency_overrides[agent_login.current_user] = _current_user
    app.dependency_overrides[get_permission_service] = lambda: _PermissionService()
    app.dependency_overrides[get_audit_service] = lambda: _AuditService()
    app.include_router(router, prefix="/api/v1")
    return app


def test_agent_login_start_queues_task(monkeypatch):
    app = _app()
    client = TestClient(app)
    pushed = []

    class _Task:
        @staticmethod
        def push(**payload):
            pushed.append(payload)

    monkeypatch.setitem(
        __import__("sys").modules,
        "src.tasks.collection.douyin_shop_login",
        type("_Module", (), {"run_login_session": _Task})(),
    )

    response = client.post(
        "/api/v1/agent-login/start",
        json={
            "phone": "13800138000",
            "account_id": "acct-1",
            "data_source_id": 7,
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "queued"
    assert body["ws_endpoint"] == f"/api/v1/agent-login/{body['session_id']}/events"
    assert f"agent_login:{body['session_id']}" in _RUN_EVENTS
    assert pushed[0] == {
        "session_id": body["session_id"],
        "phone": "13800138000",
        "account_id": "acct-1",
        "data_source_id": 7,
        "user_id": 1,
    }


def test_agent_login_start_rejects_shop_id():
    app = _app()
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent-login/start",
        json={
            "phone": "13800138000",
            "account_id": "acct-1",
            "data_source_id": 7,
            "shop_id": "1001",
        },
    )

    assert response.status_code == 422


def test_agent_login_code_submits_without_storing_plain_code(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(agent_login, "resolve_sync_redis_client", lambda: redis)
    app = _app()
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent-login/session-1/code",
        json={"code": "123456"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"ok": True}
    events = _RUN_EVENTS["agent_login:session-1"]
    assert events[-1]["event_type"] == "code_submitted"
    assert "123456" not in str(events[-1])
    assert redis.values[0][0] == "agent_login:session-1:input"
    assert ("agent_login:session-1:input", 900) in redis.expired


def test_agent_login_code_rejects_invalid_code():
    app = _app()
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent-login/session-1/code",
        json={"code": "abc"},
    )

    assert response.status_code == 422


def test_agent_login_websocket_streams_events(monkeypatch):
    async def authorize(_websocket, _permission):
        return True

    monkeypatch.setattr(agent_login, "authorize_agent_websocket", authorize)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    append_login_event(
        "session-ws",
        {"event_type": "queued", "status": "queued", "message": "queued"},
    )
    append_login_event(
        "session-ws",
        {"event_type": "run_finished", "status": "failed", "message": "done"},
    )
    client = TestClient(app)

    with client.websocket_connect("/api/v1/agent-login/session-ws/events") as websocket:
        event = websocket.receive_json()

    assert event["event_type"] == "queued"
