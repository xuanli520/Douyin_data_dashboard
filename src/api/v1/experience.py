from fastapi import APIRouter, Depends, Query

from src.auth import User, current_user
from src.auth.permissions import ExperiencePermission
from src.auth.rbac import require_permissions
from src.domains.experience.schemas import (
    ExperienceDrilldownResponse,
    ExperienceIssueListResponse,
    ExperienceOverviewResponse,
    ExperienceTrendResponse,
)
from src.domains.experience.services import (
    ExperienceQueryService,
    get_experience_service,
)
from src.exceptions import BusinessException
from src.responses.base import Response
from src.shared.errors import ErrorCode

router = APIRouter(prefix="/experience", tags=["experience"])


def _require_shop_id(shop_id: int | None) -> int:
    if shop_id is None:
        raise BusinessException(ErrorCode.DATA_VALIDATION_FAILED, "shop_id is required")
    return shop_id


@router.get("/overview")
async def get_experience_overview(
    shop_id: int | None = Query(default=None),
    date_range: str | None = Query(default="30d"),
    service: ExperienceQueryService = Depends(get_experience_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExperiencePermission.VIEW, bypass_superuser=True)),
) -> Response[ExperienceOverviewResponse]:
    shop_id = _require_shop_id(shop_id)
    data = await service.get_overview(shop_id=shop_id, date_range=date_range)
    return Response.success(data=data)


@router.get("/trend")
async def get_experience_trend(
    shop_id: int | None = Query(default=None),
    dimension: str | None = Query(default="product"),
    date_range: str | None = Query(default="30d"),
    service: ExperienceQueryService = Depends(get_experience_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExperiencePermission.VIEW, bypass_superuser=True)),
) -> Response[ExperienceTrendResponse]:
    shop_id = _require_shop_id(shop_id)
    data = await service.get_trend(
        shop_id=shop_id,
        dimension=dimension,
        date_range=date_range,
    )
    return Response.success(data=data)


@router.get("/issues")
async def get_experience_issues(
    shop_id: int | None = Query(default=None),
    dimension: str | None = Query(default="all"),
    status: str | None = Query(default="all"),
    date_range: str | None = Query(default="30d"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    service: ExperienceQueryService = Depends(get_experience_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExperiencePermission.VIEW, bypass_superuser=True)),
) -> Response[ExperienceIssueListResponse]:
    shop_id = _require_shop_id(shop_id)
    data = await service.get_issues(
        shop_id=shop_id,
        dimension=dimension,
        status=status,
        date_range=date_range,
        page=page,
        size=size,
    )
    return Response.success(data=data)


@router.get("/drilldown/{dimension}")
async def get_experience_drilldown(
    dimension: str,
    shop_id: int | None = Query(default=None),
    date_range: str | None = Query(default="30d"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    service: ExperienceQueryService = Depends(get_experience_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExperiencePermission.VIEW, bypass_superuser=True)),
) -> Response[ExperienceDrilldownResponse]:
    shop_id = _require_shop_id(shop_id)
    data = await service.get_drilldown(
        shop_id=shop_id,
        dimension=dimension,
        date_range=date_range,
        page=page,
        size=size,
    )
    return Response.success(data=data)
