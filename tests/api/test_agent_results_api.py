from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.v1.agent_results as agent_results
from src.audit import get_audit_service
from src.api.v1.agent_results import router
from src.auth.rbac import get_permission_service
from src.domains.agent_result.schemas import (
    AgentResultListResponse,
    AgentResultResponse,
)
from src.domains.agent_result.services import get_agent_result_service


async def _current_user():
    return type("_User", (), {"id": 1, "is_superuser": True, "is_active": True})()


class _AuditService:
    async def log(self, **_kwargs):
        return None


class _PermissionService:
    async def check_permissions(self, *_args, **_kwargs):
        return True


def _app(service):
    app = FastAPI()
    app.dependency_overrides[agent_results.current_user] = _current_user
    app.dependency_overrides[get_permission_service] = lambda: _PermissionService()
    app.dependency_overrides[get_audit_service] = lambda: _AuditService()
    app.dependency_overrides[get_agent_result_service] = lambda: service
    app.include_router(router, prefix="/api/v1")
    return app


def test_list_agent_results_returns_wrapped_payload():
    class _Service:
        async def list_results(self, **_kwargs):
            return AgentResultListResponse(items=[], total=0, page=1, size=50)

    response = TestClient(_app(_Service())).get("/api/v1/agent-results")

    assert response.status_code == 200
    assert response.json()["data"] == {"items": [], "total": 0, "page": 1, "size": 50}


def test_get_agent_result_returns_404_when_missing():
    class _Service:
        async def get_result(self, result_id):
            return None

    response = TestClient(_app(_Service())).get("/api/v1/agent-results/123")

    assert response.status_code == 404


def test_download_agent_results_returns_csv_file():
    class _Service:
        async def build_csv(self, **_kwargs):
            return "date,value\n2026-05-21,ok\n", "agent.csv"

    response = TestClient(_app(_Service())).get(
        "/api/v1/agent-results/download",
        params={
            "namespace": "shop_dashboard",
            "resource_key": "1001",
            "date_from": "2026-05-01",
            "date_to": "2026-05-21",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="agent.csv"'
    assert response.text == "date,value\n2026-05-21,ok\n"


def test_get_agent_result_returns_wrapped_detail():
    class _Service:
        async def get_result(self, result_id):
            return AgentResultResponse(
                id=result_id,
                namespace="shop_dashboard",
                resource_key="1001",
                resource_date=date(2026, 5, 21),
                recipe_id=1,
                output={"value": "ok"},
                status="success",
                created_at="2026-05-21T00:00:00+08:00",
                updated_at="2026-05-21T00:00:00+08:00",
            )

    response = TestClient(_app(_Service())).get("/api/v1/agent-results/7")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == 7
