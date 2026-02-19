from fastapi import APIRouter, Depends, Query

from src.api.v1.mock_data import build_orders_analysis, build_orders_trend
from src.auth import User, current_user
from src.auth.permissions import OrderPermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/orders", tags=["orders"])
EXPECTED_RELEASE = "2026-04-30"


@router.get("/trend")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_order_trend(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    dimension: str = Query(default="day"),
    user: User = Depends(current_user),
    _=Depends(require_permissions(OrderPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_orders_trend(
            shop_id=shop_id, date_range=date_range, dimension=dimension
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/analysis")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_order_analysis(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    channel: str | None = Query(default=None),
    user: User = Depends(current_user),
    _=Depends(require_permissions(OrderPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_orders_analysis(
            shop_id=shop_id, date_range=date_range, channel=channel
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
