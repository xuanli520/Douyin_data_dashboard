from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig


class SessionFactory(Protocol):
    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]: ...


class Bootstrapper(Protocol):
    def bootstrap_shops(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        shop_ids: list[str],
        verify_metric_date_by_shop: Mapping[str, str] | None = None,
    ) -> dict[str, dict[str, Any]] | Awaitable[dict[str, dict[str, Any]]]: ...

    def bootstrap_shop(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        shop_id: str,
        verify_metric_date: str | None = None,
    ) -> dict[str, Any] | Awaitable[dict[str, Any]]: ...
