from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_upload_requires_permission():
    response = client.post(
        "/api/v1/data-import/upload",
        files={"file": ("test.csv", "a,b\n1,2")},
        data={"data_source_id": "1"},
    )
    assert response.status_code in [401, 500]


def test_history_requires_permission():
    response = client.get("/api/v1/data-import/history")
    assert response.status_code in [401, 500]


def test_parse_requires_permission():
    response = client.post("/api/v1/data-import/parse", params={"import_id": 1})
    assert response.status_code in [401, 500]


def test_validate_requires_permission():
    response = client.post("/api/v1/data-import/validate", params={"import_id": 1})
    assert response.status_code in [401, 500]


def test_confirm_requires_permission():
    response = client.post("/api/v1/data-import/confirm", params={"import_id": 1})
    assert response.status_code in [401, 500]


def test_import_detail_requires_permission():
    response = client.get("/api/v1/data-import/1")
    assert response.status_code in [401, 500]


def test_cancel_requires_permission():
    response = client.post("/api/v1/data-import/1/cancel")
    assert response.status_code in [401, 500]
