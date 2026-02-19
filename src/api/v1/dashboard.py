from fastapi import APIRouter, Depends, Query

from src.api.v1.mock_data import build_dashboard_kpis, build_dashboard_overview
from src.auth import User, current_user
from src.auth.permissions import DashboardPermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
EXPECTED_RELEASE = "2026-04-30"


@router.get("/overview")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_dashboard_overview(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DashboardPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_dashboard_overview(shop_id=shop_id, date_range=date_range),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/kpis")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_dashboard_kpis(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DashboardPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_dashboard_kpis(shop_id=shop_id, date_range=date_range),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
