from fastapi import APIRouter, Depends, Query

from src.api.v1.mock_data import build_shop_score, build_shops_data
from src.auth import User, current_user
from src.auth.permissions import ShopPermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/shops", tags=["shops"])
EXPECTED_RELEASE = "2026-04-30"


@router.get("")
@in_development(
    mock_data={},
    expected_release=EXPECTED_RELEASE,
    prefer_real=True,
)
async def list_shops(
    page: int = 1,
    size: int = 20,
    date_range: str | None = Query(default="30d"),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ShopPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_shops_data(page=page, size=size, date_range=date_range),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/{shop_id}/score")
@in_development(
    mock_data={},
    expected_release=EXPECTED_RELEASE,
    prefer_real=True,
)
async def get_shop_score(
    shop_id: int,
    date_range: str | None = Query(default="30d"),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ShopPermission.SCORE, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_shop_score(shop_id=shop_id, date_range=date_range),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
