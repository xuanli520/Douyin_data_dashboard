import asyncio

import fakeredis

from src.scrapers.shop_dashboard.cookie_manager import CookieManager


async def test_cookie_manager_refreshes_cookie_when_expired():
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    manager = CookieManager(redis_client=redis_client, ttl_seconds=2)
    calls = {"count": 0}

    async def refresher() -> dict[str, str]:
        calls["count"] += 1
        return {"x_tt_token": "new-token"}

    cookie = await manager.get("shop-1", refresher=refresher)

    assert cookie["x_tt_token"] == "new-token"
    assert calls["count"] == 1


async def test_cookie_manager_uses_lock_and_refresh_only_once_for_same_shop():
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    manager = CookieManager(redis_client=redis_client, ttl_seconds=60)
    calls = {"count": 0}

    async def refresher() -> dict[str, str]:
        calls["count"] += 1
        await asyncio.sleep(0.05)
        return {"x_tt_token": "single-token"}

    first, second = await asyncio.gather(
        manager.get("shop-1", refresher=refresher),
        manager.get("shop-1", refresher=refresher),
    )

    assert first["x_tt_token"] == "single-token"
    assert second["x_tt_token"] == "single-token"
    assert calls["count"] == 1
