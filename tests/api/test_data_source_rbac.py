from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_list_data_sources_requires_permission():
    response = client.get("/api/v1/data-sources")
    assert response.status_code == 401


def test_create_data_source_requires_permission():
    response = client.post("/api/v1/data-sources", json={"name": "test"})
    assert response.status_code == 401


def test_get_data_source_requires_permission():
    response = client.get("/api/v1/data-sources/1")
    assert response.status_code == 401


def test_update_data_source_requires_permission():
    response = client.put("/api/v1/data-sources/1", json={"name": "updated"})
    assert response.status_code == 401


def test_delete_data_source_requires_permission():
    response = client.delete("/api/v1/data-sources/1")
    assert response.status_code == 401
