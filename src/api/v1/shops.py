from fastapi import APIRouter, Depends

from src.auth import current_user, User
from src.auth.rbac import require_permissions
from src.auth.permissions import ShopPermission
from src.core.endpoint_status import in_development

router = APIRouter(prefix="/shops", tags=["shops"])


@router.get("")
@in_development(
    mock_data={
        "shops": [
            {
                "id": 1,
                "name": "旗舰店",
                "category": "服装",
                "status": "active",
                "gmv": 1250000,
                "score": 4.8,
                "products_count": 256,
            }
        ],
        "total": 10,
        "page": 1,
        "size": 20,
    },
    expected_release="2026-03-01",
)
async def list_shops(
    page: int = 1,
    size: int = 20,
    user: User = Depends(current_user),
    _=Depends(require_permissions(ShopPermission.VIEW, bypass_superuser=True)),
):
    pass


@router.get("/{shop_id}/score")
@in_development(
    mock_data={
        "shop_id": 1,
        "shop_name": "旗舰店",
        "overall_score": 4.8,
        "dimensions": [
            {"name": "商品体验", "score": 4.6, "weight": 0.4, "rank": 120},
            {"name": "物流体验", "score": 4.9, "weight": 0.35, "rank": 45},
            {"name": "服务体验", "score": 4.7, "weight": 0.25, "rank": 89},
        ],
        "trend": [
            {"date": "2026-01-01", "score": 4.7},
            {"date": "2026-01-08", "score": 4.75},
            {"date": "2026-01-15", "score": 4.8},
        ],
    },
    expected_release="2026-03-01",
)
async def get_shop_score(
    shop_id: int,
    user: User = Depends(current_user),
    _=Depends(require_permissions(ShopPermission.SCORE, bypass_superuser=True)),
):
    pass
