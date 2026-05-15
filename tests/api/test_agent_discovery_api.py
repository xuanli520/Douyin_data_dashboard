from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.agent_discovery import _RUN_EVENTS
from src.api.v1.agent_discovery import router


def test_agent_discovery_trigger_returns_run_id(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
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
        json={"goal": "find value", "entrypoint_url": "https://example.test"},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "queued"
    assert body["run_id"] in _RUN_EVENTS
    assert pushed[0]["run_id"] == body["run_id"]


def test_agent_discovery_trigger_rejects_empty_goal():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent-discovery",
        json={"goal": "", "entrypoint_url": "https://example.test"},
    )

    assert response.status_code == 422
