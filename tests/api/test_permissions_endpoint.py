from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_get_current_user_permissions_requires_auth():
    response = client.get("/api/v1/permissions/me")
    assert response.status_code == 401
