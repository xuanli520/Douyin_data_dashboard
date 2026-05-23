from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.v1.agent_discovery as agent_discovery
from src.audit import get_audit_service
from src.api.v1.agent_discovery import router
from src.auth.rbac import get_permission_service
from src.domains.agent_recipe.schemas import AgentRecipeImportResponse
from src.domains.agent_recipe.services import get_agent_recipe_service


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
    app.dependency_overrides[agent_discovery.current_user] = _current_user
    app.dependency_overrides[get_permission_service] = lambda: _PermissionService()
    app.dependency_overrides[get_audit_service] = lambda: _AuditService()
    app.dependency_overrides[get_agent_recipe_service] = lambda: service
    app.include_router(router, prefix="/api/v1")
    return app


def test_export_agent_recipe_returns_recipe_json_file():
    class _Service:
        async def export_recipe(self, recipe_id):
            return (
                {
                    "format_version": 1,
                    "recipe": {
                        "namespace": "shop_dashboard",
                        "key": "overview",
                        "version": 3,
                        "entrypoint": {"url": "https://example.com"},
                        "steps": [],
                        "observations": {},
                        "assertions": [],
                        "recovery_policy": {},
                        "security_policy": {},
                    },
                },
                "shop_dashboard_overview_v3.agent-recipe.json",
            )

    response = TestClient(_app(_Service())).get(
        "/api/v1/agent-discovery/recipes/12/export"
    )

    assert response.status_code == 200
    assert response.json()["recipe"]["version"] == 3
    assert response.headers["content-disposition"] == (
        'attachment; filename="shop_dashboard_overview_v3.agent-recipe.json"'
    )


def test_export_agent_recipe_returns_404_when_missing():
    class _Service:
        async def export_recipe(self, recipe_id):
            return None

    response = TestClient(_app(_Service())).get(
        "/api/v1/agent-discovery/recipes/12/export"
    )

    assert response.status_code == 404


def test_import_agent_recipe_returns_created_recipe():
    class _Service:
        async def import_recipe(self, content):
            assert b'"format_version": 1' in content
            return AgentRecipeImportResponse(
                id=1,
                namespace="shop_dashboard",
                key="overview",
                version=3,
                status="active",
                stability="candidate",
            )

    response = TestClient(_app(_Service())).post(
        "/api/v1/agent-discovery/recipes/import",
        files={
            "file": (
                "overview.agent-recipe.json",
                b'{"format_version": 1, "recipe": {"namespace": "shop_dashboard"}}',
                "application/json",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["stability"] == "candidate"


def test_import_agent_recipe_returns_409_on_conflict():
    class _Service:
        async def import_recipe(self, content):
            return None

    response = TestClient(_app(_Service())).post(
        "/api/v1/agent-discovery/recipes/import",
        files={
            "file": (
                "overview.agent-recipe.json",
                b'{"format_version": 1, "recipe": {"namespace": "shop_dashboard"}}',
                "application/json",
            )
        },
    )

    assert response.status_code == 409
