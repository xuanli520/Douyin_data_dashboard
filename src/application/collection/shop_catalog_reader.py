from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.collection.account_shop_catalog_service import (
    AccountShopCatalogService,
)
from src.domains.data_source.enums import DataSourceType
from src.domains.data_source.repository import DataSourceRepository
from src.exceptions import BusinessException
from src.session import get_session
from src.shared.errors import ErrorCode


@dataclass(frozen=True, slots=True)
class ShopDashboardShopCatalogView:
    data_source_id: int
    account_id: str
    shop_ids: list[str]
    catalog_stale: bool
    resolve_source: str


class ShopDashboardShopCatalogReader:
    def __init__(
        self,
        *,
        data_source_repo: DataSourceRepository,
        catalog_service: AccountShopCatalogService | None = None,
    ) -> None:
        self.data_source_repo = data_source_repo
        self.catalog_service = catalog_service or AccountShopCatalogService()

    async def get_for_data_source(
        self,
        data_source_id: int,
        *,
        force_refresh: bool = False,
    ) -> ShopDashboardShopCatalogView:
        data_source = await self.data_source_repo.get_by_id(data_source_id)
        if data_source is None:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND,
                "DataSource not found",
            )
        if data_source.source_type != DataSourceType.DOUYIN_SHOP:
            raise BusinessException(
                ErrorCode.DATASOURCE_UNSUPPORTED_TYPE,
                "Shop catalog is only supported for DOUYIN_SHOP",
            )

        extra_config = dict(data_source.extra_config or {})
        account_id = _resolve_account_id(
            extra_config,
            data_source_id=data_source.id or data_source_id,
        )
        catalog = await self.catalog_service.get_shop_catalog(
            account_id=account_id,
            cookies=_extract_cookies(extra_config),
            common_query=_as_dict(extra_config.get("common_query")),
            extra_config=extra_config,
            force_refresh=force_refresh,
        )
        return ShopDashboardShopCatalogView(
            data_source_id=int(data_source.id or data_source_id),
            account_id=account_id,
            shop_ids=list(catalog.shop_ids),
            catalog_stale=bool(catalog.catalog_stale),
            resolve_source=catalog.resolve_source,
        )


def _resolve_account_id(config: Mapping[str, Any], *, data_source_id: int) -> str:
    login_state = _as_dict(config.get("shop_dashboard_login_state"))
    meta = _as_dict(config.get("shop_dashboard_login_state_meta"))
    credentials = _as_dict(login_state.get("credentials"))
    return (
        _text(config.get("account_id"))
        or _text(meta.get("account_id"))
        or _text(login_state.get("account_id"))
        or _text(credentials.get("account_id"))
        or _text(config.get("user_phone"))
        or f"data_source_{data_source_id}"
    )


def _extract_cookies(config: Mapping[str, Any]) -> dict[str, str]:
    login_state = _as_dict(config.get("shop_dashboard_login_state"))
    storage_state = _as_dict(login_state.get("storage_state"))
    storage_state_cookies = _parse_storage_state_cookie_mapping(storage_state)
    if storage_state_cookies:
        return storage_state_cookies
    return _parse_cookie_mapping(config.get("cookies"))


def _parse_storage_state_cookie_mapping(
    storage_state: Mapping[str, Any],
) -> dict[str, str]:
    cookies = storage_state.get("cookies")
    if not isinstance(cookies, list):
        return {}
    result: dict[str, str] = {}
    for item in cookies:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name")
        value = item.get("value")
        if name is None or value is None:
            continue
        result[str(name)] = str(value)
    return result


def _parse_cookie_mapping(value: Any) -> dict[str, str]:
    if isinstance(value, Mapping):
        return {str(key): str(item) for key, item in value.items() if item is not None}
    if not isinstance(value, str):
        return {}
    text = value.strip()
    if not text:
        return {}
    cookie = SimpleCookie()
    try:
        cookie.load(text)
    except CookieError:
        cookie.clear()
    parsed = {
        key: morsel.value
        for key, morsel in cookie.items()
        if key and morsel.value is not None
    }
    if parsed:
        return parsed
    result: dict[str, str] = {}
    for pair in [item.strip() for item in text.split(";") if item.strip()]:
        if "=" not in pair:
            continue
        key, raw_value = pair.split("=", 1)
        if key.strip():
            result[key.strip()] = raw_value.strip()
    return result


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


async def get_shop_dashboard_shop_catalog_reader(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[ShopDashboardShopCatalogReader, None]:
    yield ShopDashboardShopCatalogReader(
        data_source_repo=DataSourceRepository(session=session),
    )
