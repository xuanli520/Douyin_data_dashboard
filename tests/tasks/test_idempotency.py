from concurrent.futures import ThreadPoolExecutor

import fakeredis

from src.tasks.idempotency import FunboostIdempotencyHelper


def test_idempotency_refresh_lock_in_concurrent_context():
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    helper = FunboostIdempotencyHelper(redis_client, "sync_shop_dashboard")
    business_key = "shop-1:2026-03-03"
    lock_key = f"douyin:lock:sync_shop_dashboard:{business_key}"

    def _fake_eval(_script, _numkeys, key, token, ttl):
        current = redis_client.get(key)
        if current == token:
            redis_client.expire(key, int(ttl))
            return 1
        return 0

    redis_client.eval = _fake_eval

    token = helper.acquire_lock(business_key, ttl=120)
    assert token is not None

    def _refresh_ok():
        return helper.refresh_lock(business_key, token, 600)

    def _refresh_with_wrong_token():
        return helper.refresh_lock(business_key, "wrong-token", 600)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_refresh_ok),
            pool.submit(_refresh_with_wrong_token),
        ]
        results = [future.result() for future in futures]

    assert True in results
    assert False in results
    assert redis_client.ttl(lock_key) > 0
