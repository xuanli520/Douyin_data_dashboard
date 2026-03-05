from types import SimpleNamespace


class _FakeRedis:
    def hset(self, _key, _mapping):
        return None

    def expire(self, _key, _seconds):
        return None


def test_agent_task_pushes_cold_metric_collection(monkeypatch):
    from src.tasks.collection import douyin_shop_agent as module

    monkeypatch.setattr(
        module.sync_shop_dashboard_agent,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )
    monkeypatch.setattr(module.fct, "task_id", "task-llm-1", raising=False)

    class _FakeIdempotencyHelper:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_cached_result(self, _key):
            return None

        def acquire_lock(self, _key, ttl):
            return "token-1"

        def cache_result(self, _key, _result, _ttl=86400):
            return None

        def release_lock(self, _key, _token):
            return None

    class FakeAgent:
        def supplement_cold_data(self, result, shop_id, date, reason):
            assert result == {}
            assert shop_id == "shop-1"
            assert reason == "cold_metric"
            return {
                "violations_detail": [{"id": "v-1"}],
                "arbitration_detail": [{"id": "a-1"}],
                "dsr_trend": [{"date": date, "score": 4.7}],
            }

    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    monkeypatch.setattr(module, "LLMDashboardAgent", lambda: FakeAgent())

    result = module.sync_shop_dashboard_agent(
        "shop-1",
        "2026-03-03",
        reason="cold_metric",
    )

    assert result["status"] == "success"
    assert result["source"] == "llm"
    assert result["reason"] == "cold_metric"
    assert result["violations_detail"] == [{"id": "v-1"}]
