from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.v1.metrics as metrics
from src.audit import get_audit_service
from src.api.v1.metrics import router
from src.auth.rbac import get_permission_service
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
    app.dependency_overrides[metrics.current_user] = _current_user
    app.dependency_overrides[get_permission_service] = lambda: _PermissionService()
    app.dependency_overrides[get_audit_service] = lambda: _AuditService()
    app.dependency_overrides[get_agent_result_service] = lambda: service
    app.include_router(router, prefix="/api/v1")
    return app


def test_download_metric_detail_uses_recipe_key_mapping():
    calls = []

    class _Service:
        async def build_csv_by_recipe_key(self, **kwargs):
            calls.append(kwargs)
            return "date,metric\n2026-05-20,product\n", "metric.csv"

    response = TestClient(_app(_Service())).get(
        "/api/v1/metrics/product/download",
        params={
            "shop_id": 1001,
            "date_from": "2026-05-20",
            "date_to": "2026-05-21",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text == "date,metric\n2026-05-20,product\n"
    assert calls[0]["namespace"] == "douyin_shop_dashboard"
    assert calls[0]["resource_key"] == "1001"
    assert calls[0]["recipe_key"] == "experience_score_product_detail"
