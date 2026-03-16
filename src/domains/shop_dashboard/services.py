from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.session import get_session


class ShopDashboardQueryService:
    def __init__(self, repo: ShopDashboardRepository):
        self.repo = repo

    async def list_shops(self) -> dict[str, Any]:
        items = await self.repo.list_shops()
        return {"items": items}

    async def query(
        self,
        *,
        shop_id: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        query_start = min(start_date, end_date)
        query_end = max(start_date, end_date)
        items = await self.repo.list_display_materials(
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


async def get_shop_dashboard_query_service(
    session: AsyncSession = Depends(get_session),
) -> ShopDashboardQueryService:
    return ShopDashboardQueryService(repo=ShopDashboardRepository(session=session))
