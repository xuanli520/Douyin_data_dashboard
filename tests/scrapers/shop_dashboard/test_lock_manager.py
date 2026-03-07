import fakeredis

from src.scrapers.shop_dashboard.lock_manager import LockManager


def test_lock_manager_keys():
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    lock = LockManager(redis_client=fake_redis)
    assert lock.account_lock_key("acct-1") == "douyin:account:lock:acct-1"
    assert lock.shop_lock_key("shop-1") == "douyin:shop:lock:shop-1"
