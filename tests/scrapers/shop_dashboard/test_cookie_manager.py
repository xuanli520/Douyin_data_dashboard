import fakeredis

from src.scrapers.shop_dashboard.cookie_manager import CookieManager


def test_cookie_manager_no_longer_writes_cookie_to_redis():
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    manager = CookieManager(redis_client=fake_redis)

    manager.set("acct-1", {"x_tt_token": "abc"})

    assert fake_redis.hgetall("douyin:shop_dashboard:cookie:acct-1") == {}
