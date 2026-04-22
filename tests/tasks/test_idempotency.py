import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import fakeredis
from redis.exceptions import RedisError

from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.tasks.collection import douyin_shop_dashboard as collection_module
from src.tasks.collection.shop_dashboard_plan_builder import CollectionPlanUnit
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


class _EvalFailRedis:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self.expire_called = False
        self.delete_called = False

    def set(self, key, value, ex=None, nx=False):
        _ = ex
        if nx and key in self._values:
            return False
        self._values[key] = value
        return True

    def get(self, key):
        return self._values.get(key)

    def eval(self, _script, _numkeys, *_args):
        raise RedisError("eval failed")

    def expire(self, *_args):
        self.expire_called = True
        return True

    def delete(self, *_args):
        self.delete_called = True
        return 1


class _RegisterScriptRedis(_EvalFailRedis):
    def register_script(self, script):
        def _runner(*, keys, args, client=None):
            _ = (script, client)
            key = str(keys[0])
            token = args[0]
            ttl = int(args[1])
            if self._values.get(key) != token:
                return 0
            self.expire(key, ttl)
            return 1

        return _runner


def test_idempotency_refresh_lock_retries_with_register_script():
    redis_client = _RegisterScriptRedis()
    helper = FunboostIdempotencyHelper(redis_client, "sync_shop_dashboard")
    business_key = "shop-1:2026-03-03"

    token = helper.acquire_lock(business_key, ttl=120)
    assert token is not None
    assert helper.refresh_lock(business_key, token, 600) is True
    assert redis_client.expire_called is True


def test_idempotency_release_lock_does_not_fallback_to_non_atomic_delete(caplog):
    redis_client = _EvalFailRedis()
    helper = FunboostIdempotencyHelper(redis_client, "sync_shop_dashboard")
    business_key = "shop-1:2026-03-03"

    token = helper.acquire_lock(business_key, ttl=120)
    assert token is not None

    with caplog.at_level(logging.ERROR):
        helper.release_lock(business_key, token)

    assert redis_client.delete_called is False
    assert "failed to release idempotency lock" in caplog.text


def test_build_business_key_supports_extended_dedupe_variables():
    runtime = ShopDashboardRuntimeConfig(
        shop_mode="EXACT",
        resolved_shop_ids=["shop-1"],
        catalog_stale=False,
        shop_id="shop-1",
        cookies={},
        proxy=None,
        timeout=15,
        retry_count=3,
        rate_limit=100,
        granularity="DAY",
        time_range=None,
        incremental_mode="BY_DATE",
        backfill_last_n_days=1,
        data_latency="T+1",
        target_type="SHOP_OVERVIEW",
        metrics=[],
        dimensions=[],
        filters={},
        top_n=None,
        include_long_tail=False,
        session_level=False,
        dedupe_key=(
            "{shop_id}:{granularity}:{window_start}:{window_end}:{rule_id}:{execution_id}"
        ),
        rule_id=2,
        execution_id="exec-1",
        fallback_chain=("http",),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=["overview"],
    )
    plan_unit = CollectionPlanUnit(
        target_shop_id="shop-1",
        window_start=datetime.fromisoformat("2026-03-03T00:00:00"),
        window_end=datetime.fromisoformat("2026-03-03T23:59:59"),
        metric_date="2026-03-03",
        granularity="DAY",
        effective_filters={
            "shop_id": "shop-1",
            "date_range": None,
            "cursor": None,
            "extra_filters": {},
        },
        plan_index=0,
    )

    key = collection_module._build_business_key(
        runtime,
        "2026-03-03",
        plan_unit=plan_unit,
    )

    assert key == ("shop-1:DAY:2026-03-03T00:00:00:2026-03-03T23:59:59:2:exec-1")
