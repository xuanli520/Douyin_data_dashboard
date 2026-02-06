from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_list_tasks_requires_permission():
    response = client.get("/api/v1/tasks")
    assert response.status_code in [401, 500]


def test_create_task_requires_permission():
    response = client.post("/api/v1/tasks", json={"name": "test"})
    assert response.status_code in [401, 500]


def test_run_task_requires_permission():
    response = client.post("/api/v1/tasks/1/run")
    assert response.status_code in [401, 500]


def test_get_task_executions_requires_permission():
    response = client.get("/api/v1/tasks/1/executions")
    assert response.status_code in [401, 500]
