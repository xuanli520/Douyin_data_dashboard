from fastapi import APIRouter, Depends, Query

from src.auth import User, current_user
from src.auth.permissions import DashboardPermission
from src.auth.rbac import require_permissions
from src.domains.experience.schemas import (
    DashboardKpisResponse,
    DashboardOverviewResponse,
)
from src.domains.experience.services import (
    ExperienceQueryService,
    get_experience_service,
)
from src.responses.base import Response

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
async def get_dashboard_overview(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    service: ExperienceQueryService = Depends(get_experience_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DashboardPermission.VIEW, bypass_superuser=True)),
) -> Response[DashboardOverviewResponse]:
    data = await service.get_dashboard_overview(
        shop_id=shop_id,
        date_range=date_range,
    )
    return Response.success(data=data)


@router.get("/kpis")
async def get_dashboard_kpis(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    service: ExperienceQueryService = Depends(get_experience_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DashboardPermission.VIEW, bypass_superuser=True)),
) -> Response[DashboardKpisResponse]:
    data = await service.get_dashboard_kpis(
        shop_id=shop_id,
        date_range=date_range,
    )
    return Response.success(data=data)
