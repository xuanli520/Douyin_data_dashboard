from __future__ import annotations

import csv
import io
from datetime import date
from datetime import timedelta
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.session import get_session


class ShopDashboardQueryService:
    def __init__(self, repo: ShopDashboardRepository):
        self.repo = repo

    async def list_shops(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        query_start = min(start_date, end_date) if start_date and end_date else None
        query_end = max(start_date, end_date) if start_date and end_date else None
        items = await self.repo.list_shops(
            start_date=query_start,
            end_date=query_end,
        )
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

    async def build_all_shops_csv(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[str, str]:
        query_start, query_end = _resolve_date_range(date_from, date_to)
        items = await self.repo.list_latest_per_shop(
            start_date=query_start,
            end_date=query_end,
        )
        return (
            _build_scores_csv(items),
            f"shop_scores_{query_start.isoformat()}_{query_end.isoformat()}.csv",
        )

    async def build_shop_scores_csv(
        self,
        *,
        shop_id: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[str, str]:
        query_start, query_end = _resolve_date_range(date_from, date_to)
        items = await self.repo.list_display_materials(
            shop_id=shop_id,
            start_date=query_start,
            end_date=query_end,
        )
        return (
            _build_scores_csv(items),
            f"shop_{shop_id}_scores_{query_start.isoformat()}_{query_end.isoformat()}.csv",
        )


async def get_shop_dashboard_query_service(
    session: AsyncSession = Depends(get_session),
) -> ShopDashboardQueryService:
    return ShopDashboardQueryService(repo=ShopDashboardRepository(session=session))


def _resolve_date_range(
    date_from: date | None,
    date_to: date | None,
) -> tuple[date, date]:
    query_end = date_to or date.today()
    query_start = date_from or query_end - timedelta(days=29)
    return min(query_start, query_end), max(query_start, query_end)


def _build_scores_csv(items: list[dict[str, Any]]) -> str:
    headers = [
        "shop_id",
        "shop_name",
        "metric_date",
        "total_score",
        "product_score",
        "logistics_score",
        "service_score",
        "bad_behavior_score",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(items)
    return buffer.getvalue()
