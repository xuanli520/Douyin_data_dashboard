from fastapi import APIRouter, Depends, Query

from src.api.v1.mock_data import build_after_sales_causes, build_after_sales_refund_rate
from src.auth import User, current_user
from src.auth.permissions import AfterSalePermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/after-sales", tags=["after-sales"])
EXPECTED_RELEASE = "2026-04-30"


@router.get("/refund-rate")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_refund_rate(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    user: User = Depends(current_user),
    _=Depends(require_permissions(AfterSalePermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_after_sales_refund_rate(shop_id=shop_id, date_range=date_range),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/causes")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_refund_causes(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(current_user),
    _=Depends(require_permissions(AfterSalePermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_after_sales_causes(
            shop_id=shop_id,
            date_range=date_range,
            page=page,
            size=size,
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
