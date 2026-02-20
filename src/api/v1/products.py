from fastapi import APIRouter, Depends, Query

from src.api.v1.mock_data import build_products_funnel, build_products_ranking
from src.auth import User, current_user
from src.auth.permissions import ProductPermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/products", tags=["products"])
EXPECTED_RELEASE = "2026-04-30"


@router.get("/funnel")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_product_funnel(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    product_id: int | None = Query(default=None),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ProductPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_products_funnel(
            shop_id=shop_id,
            date_range=date_range,
            product_id=product_id,
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/ranking")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_product_ranking(
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    metric: str = Query(default="sales"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ProductPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_products_ranking(
            shop_id=shop_id,
            date_range=date_range,
            metric=metric,
            page=page,
            size=size,
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
