from fastapi import APIRouter, Depends, Query

from src.api.v1.mock_data import (
    SUPPORTED_EXPERIENCE_DIMENSIONS,
    build_experience_drilldown,
    build_experience_issues,
    build_experience_overview,
    build_experience_trend,
    normalize_dimension,
)
from src.auth import User, current_user
from src.auth.permissions import ExperiencePermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/experience", tags=["experience"])
EXPECTED_RELEASE = "2026-04-30"


@router.get("/overview")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_experience_overview(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExperiencePermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_experience_overview(shop_id=shop_id, date_range=date_range),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/trend")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_experience_trend(
    shop_id: int = Query(default=1001),
    dimension: str | None = Query(default="product"),
    date_range: str | None = Query(default="30d"),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExperiencePermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_experience_trend(
            shop_id=shop_id,
            dimension=normalize_dimension(dimension),
            date_range=date_range,
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/issues")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_experience_issues(
    shop_id: int = Query(default=1001),
    dimension: str | None = Query(default="all"),
    status: str | None = Query(default="all"),
    date_range: str | None = Query(default="30d"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExperiencePermission.VIEW, bypass_superuser=True)),
):
    normalized_dimension = (
        dimension if dimension == "all" else normalize_dimension(dimension)
    )
    raise EndpointInDevelopmentException(
        data=build_experience_issues(
            shop_id=shop_id,
            dimension=normalized_dimension,
            status=status,
            date_range=date_range,
            page=page,
            size=size,
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/drilldown/{dimension}")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_experience_drilldown(
    dimension: str,
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExperiencePermission.VIEW, bypass_superuser=True)),
):
    normalized = (
        dimension if dimension in SUPPORTED_EXPERIENCE_DIMENSIONS else "product"
    )
    raise EndpointInDevelopmentException(
        data=build_experience_drilldown(
            shop_id=shop_id,
            dimension=normalized,
            date_range=date_range,
            page=page,
            size=size,
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
