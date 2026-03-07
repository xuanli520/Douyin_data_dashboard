from __future__ import annotations

from datetime import UTC, date as date_type, datetime
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import User, current_user
from src.auth.permissions import ShopDashboardPermission
from src.auth.rbac import require_permissions
from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.exceptions import (
    TaskNotFoundException,
    TaskPushFailedException,
    TaskStatusBackendUnavailableException,
)
from src.session import get_session
from src.tasks.collection.douyin_shop_dashboard import sync_shop_dashboard

router = APIRouter(prefix="/shop-dashboard", tags=["shop-dashboard"])


class ShopDashboardTriggerItem(BaseModel):
    data_source_id: int = Field(ge=1)
    rule_id: int = Field(ge=1)
    execution_id: str | None = None


class ShopDashboardBatchTriggerPayload(BaseModel):
    items: list[ShopDashboardTriggerItem] = Field(min_length=1)


@lru_cache(maxsize=1)
def _get_redis_client() -> Redis:
    from src.config import get_settings

    settings = get_settings()
    cache_settings = settings.cache
    status_db = settings.funboost.filter_and_rpc_result_redis_db
    if cache_settings.password:
        url = (
            f"redis://:{cache_settings.password}@"
            f"{cache_settings.host}:{cache_settings.port}/{status_db}"
        )
    else:
        url = f"redis://{cache_settings.host}:{cache_settings.port}/{status_db}"
    return Redis.from_url(url, decode_responses=True)


@router.post("/batch-trigger")
async def batch_trigger(
    payload: ShopDashboardBatchTriggerPayload,
    user: User = Depends(current_user),
    _=Depends(
        require_permissions(ShopDashboardPermission.TRIGGER, bypass_superuser=True)
    ),
) -> dict[str, Any]:
    now_text = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    items: list[dict[str, Any]] = []
    for index, item in enumerate(payload.items, start=1):
        execution_id = item.execution_id or f"api-{now_text}-{index}"
        async_result = sync_shop_dashboard.push(
            data_source_id=item.data_source_id,
            rule_id=item.rule_id,
            execution_id=execution_id,
            triggered_by=user.id,
        )
        task_id = str(getattr(async_result, "task_id", "") or "")
        if not task_id:
            raise TaskPushFailedException()
        items.append(
            {
                "task_id": task_id,
                "data_source_id": item.data_source_id,
                "rule_id": item.rule_id,
                "execution_id": execution_id,
            }
        )
    return {"items": items}


@router.get("/status/{task_id}")
async def get_status(
    task_id: str,
    user: User = Depends(current_user),
    _=Depends(
        require_permissions(ShopDashboardPermission.STATUS, bypass_superuser=True)
    ),
) -> dict[str, Any]:
    _ = user
    redis_client = _get_redis_client()
    key = f"douyin:task:status:{task_id}"
    try:
        data = redis_client.hgetall(key)
    except RedisError as exc:
        raise TaskStatusBackendUnavailableException() from exc
    if not data:
        raise TaskNotFoundException(task_id=task_id)
    return {"task_id": task_id, "status": data}


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
