from __future__ import annotations

from datetime import date as date_type
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import User, current_user
from src.auth.permissions import ShopDashboardPermission
from src.auth.rbac import require_permissions
from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.session import get_session

router = APIRouter(prefix="/shop-dashboard", tags=["shop-dashboard"])


@router.get("/query")
async def query(
    shop_id: str = Query(min_length=1),
    start_date: date_type = Query(),
    end_date: date_type = Query(),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
    _=Depends(
        require_permissions(ShopDashboardPermission.QUERY, bypass_superuser=True)
    ),
) -> dict[str, Any]:
    _ = user
    query_start = min(start_date, end_date)
    query_end = max(start_date, end_date)
    repo = ShopDashboardRepository(session)
    items = await repo.query_dashboard_results(
        shop_id=shop_id,
        start_date=query_start,
        end_date=query_end,
    )
    return {
        "shop_id": shop_id,
        "start_date": query_start.isoformat(),
        "end_date": query_end.isoformat(),
        "items": items,
    }
