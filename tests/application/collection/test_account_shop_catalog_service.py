from __future__ import annotations

import json
import time

import pytest

from src.application.collection.account_shop_catalog_service import (
    AccountShopCatalogService,
)
from src.shared.redis_keys import redis_keys


class _FailingResolver:
    async def resolve_shop_ids(self, **_kwargs):
        raise RuntimeError("catalog_refresh_failed")


class _FakeRedis:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, key: str):
        return self._data.get(key)

    def set(self, key: str, value, ex=None, nx=False):
        _ = ex
        if nx and key in self._data:
            return False
        self._data[key] = str(value)
        return True

    def delete(self, key: str):
        self._data.pop(key, None)
        return 1


@pytest.mark.asyncio
async def test_catalog_stale_fallback_should_respect_stale_allow_window():
    account_id = "acct-1"
    redis_client = _FakeRedis()
    catalog_key = redis_keys.shop_dashboard_shop_catalog(account_id=account_id)
    redis_client._data[catalog_key] = json.dumps(
        {
            "shop_ids": ["shop-expired"],
            "updated_at": int(time.time()) - 9000,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    service = AccountShopCatalogService(
        account_shop_resolver=_FailingResolver(),
        redis_client=redis_client,
    )

    with pytest.raises(RuntimeError, match="catalog_refresh_failed"):
        await service.get_shop_catalog(
            account_id=account_id,
            cookies={"sid": "token"},
            force_refresh=True,
        )
