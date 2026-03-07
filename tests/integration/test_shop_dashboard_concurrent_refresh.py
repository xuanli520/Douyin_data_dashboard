import asyncio

import fakeredis

from src.scrapers.shop_dashboard.lock_manager import LockManager
from src.scrapers.shop_dashboard.login_state_manager import LoginStateManager
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


async def test_concurrent_refresh(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    store.save("acct-1", {"cookies": [{"name": "sid", "value": "v"}], "origins": []})
    manager = LoginStateManager(state_store=store)
    lock_manager = LockManager(redis_client=fakeredis.FakeRedis(decode_responses=True))

    async def refresh_once():
        token = lock_manager.acquire_account_lock("acct-1", ttl_seconds=60)
        if not token:
            return "locked"
        try:
            await asyncio.sleep(0.05)
            return await manager.check_and_refresh("acct-1")
        finally:
            lock_manager.release_account_lock("acct-1", token)

    first, second = await asyncio.gather(refresh_once(), refresh_once())

    assert {first, second} == {True, "locked"}
