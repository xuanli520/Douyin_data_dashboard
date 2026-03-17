from __future__ import annotations

from datetime import date as date_type
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.auth import User, current_user
from src.auth.permissions import ShopPermission
from src.auth.rbac import require_permissions
from src.domains.shop_dashboard.services import (
    ShopDashboardQueryService,
    get_shop_dashboard_query_service,
)

router = APIRouter(prefix="/shops", tags=["shops"])


@router.get("")
async def query_shop_dashboard(
    shop_id: str | None = Query(default=None, min_length=1),
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
    service: ShopDashboardQueryService = Depends(get_shop_dashboard_query_service),
    _user: User = Depends(current_user),
    _=Depends(require_permissions(ShopPermission.VIEW, bypass_superuser=True)),
) -> dict[str, Any]:
    if shop_id is None and start_date is None and end_date is None:
        return await service.list_shops()

    if shop_id is None or start_date is None or end_date is None:
        raise HTTPException(
            status_code=422,
            detail="shop_id, start_date, end_date must be provided together",
        )

    return await service.query(
        shop_id=shop_id,
        start_date=start_date,
        end_date=end_date,
    )
