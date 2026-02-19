from fastapi import APIRouter, Depends, Query

from src.api.v1.mock_data import build_sales_by_channel, build_sales_summary
from src.auth import User, current_user
from src.auth.permissions import SalePermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/sales", tags=["sales"])
EXPECTED_RELEASE = "2026-04-30"


@router.get("/summary")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_sales_summary(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    dimension: str = Query(default="day"),
    user: User = Depends(current_user),
    _=Depends(require_permissions(SalePermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_sales_summary(
            shop_id=shop_id, date_range=date_range, dimension=dimension
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/by-channel")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_sales_by_channel(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    user: User = Depends(current_user),
    _=Depends(require_permissions(SalePermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_sales_by_channel(shop_id=shop_id, date_range=date_range),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
