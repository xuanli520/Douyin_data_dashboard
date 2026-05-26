from __future__ import annotations

from datetime import date as date_type
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.auth import User, current_user
from src.auth.permissions import ShopPermission
from src.auth.rbac import require_permissions
from src.domains.shop_dashboard.services import (
    ShopDashboardQueryService,
    get_shop_dashboard_query_service,
)

router = APIRouter(prefix="/shops", tags=["shops"])


@router.get("/scores/csv", response_class=StreamingResponse)
async def download_all_shop_scores_csv(
    date_from: date_type | None = Query(default=None),
    date_to: date_type | None = Query(default=None),
    service: ShopDashboardQueryService = Depends(get_shop_dashboard_query_service),
    _user: User = Depends(current_user),
    _=Depends(require_permissions(ShopPermission.VIEW, bypass_superuser=True)),
) -> StreamingResponse:
    csv_content, filename = await service.build_all_shops_csv(
        date_from=date_from,
        date_to=date_to,
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{shop_id}/scores/csv", response_class=StreamingResponse)
async def download_shop_scores_csv(
    shop_id: str,
    date_from: date_type | None = Query(default=None),
    date_to: date_type | None = Query(default=None),
    service: ShopDashboardQueryService = Depends(get_shop_dashboard_query_service),
    _user: User = Depends(current_user),
    _=Depends(require_permissions(ShopPermission.VIEW, bypass_superuser=True)),
) -> StreamingResponse:
    csv_content, filename = await service.build_shop_scores_csv(
        shop_id=shop_id,
        date_from=date_from,
        date_to=date_to,
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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

    if shop_id is None and start_date is not None and end_date is not None:
        return await service.list_shops(start_date=start_date, end_date=end_date)

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
