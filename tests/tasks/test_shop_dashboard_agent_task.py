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

    async def _fake_load_agent_context(shop_id: str, metric_date: str, reason: str):
        assert shop_id == "shop-1"
        assert metric_date == "2026-03-03"
        assert reason == "cold_metric"
        return {
            "raw": {"html": "<div>snapshot</div>"},
            "violations_detail": [{"id": "existing-v"}],
        }

    persisted: list[dict] = []

    async def _fake_persist_agent_patch(
        shop_id: str,
        metric_date: str,
        reason: str,
        patch: dict,
    ) -> None:
        persisted.append(
            {
                "shop_id": shop_id,
                "metric_date": metric_date,
                "reason": reason,
                "patch": patch,
            }
        )

    class FakeAgent:
        def supplement_cold_data(self, result, shop_id, date, reason):
            assert result["raw"]["html"] == "<div>snapshot</div>"
            assert result["violations_detail"] == [{"id": "existing-v"}]
            assert shop_id == "shop-1"
            assert reason == "cold_metric"
            return {
                "violations_detail": [{"id": "v-1"}],
                "arbitration_detail": [{"id": "a-1"}],
                "dsr_trend": [{"date": date, "score": 4.7}],
            }

    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    monkeypatch.setattr(module, "LLMDashboardAgent", lambda: FakeAgent())
    monkeypatch.setattr(module, "_load_agent_context", _fake_load_agent_context)
    monkeypatch.setattr(module, "_persist_agent_patch", _fake_persist_agent_patch)

    result = module.sync_shop_dashboard_agent(
        "shop-1",
        "2026-03-03",
        reason="cold_metric",
    )

    assert result["status"] == "success"
    assert result["source"] == "llm"
    assert result["reason"] == "cold_metric"
    assert result["violations_detail"] == [{"id": "v-1"}]
    assert len(persisted) == 1
    assert persisted[0]["shop_id"] == "shop-1"


def test_agent_task_uses_current_date_when_date_missing(monkeypatch):
    from src.tasks.collection import douyin_shop_agent as module

    monkeypatch.setattr(
        module.sync_shop_dashboard_agent,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )
    monkeypatch.setattr(module.fct, "task_id", "task-llm-2", raising=False)

    class _FakeIdempotencyHelper:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_cached_result(self, _key):
            return None

        def acquire_lock(self, _key, ttl):
            _ = ttl
            return "token-1"

        def cache_result(self, _key, _result, _ttl=86400):
            return None

        def release_lock(self, _key, _token):
            return None

    class _FrozenDatetime:
        @staticmethod
        def now(_tz):
            from datetime import datetime

            return datetime(2026, 3, 4)

    async def _fake_load_agent_context(shop_id: str, metric_date: str, reason: str):
        assert shop_id == "shop-1"
        assert metric_date == "2026-03-04"
        assert reason == "cold_metric"
        return {"raw": {}}

    async def _fake_persist_agent_patch(
        shop_id: str,
        metric_date: str,
        reason: str,
        patch: dict,
    ) -> None:
        _ = (shop_id, metric_date, reason, patch)

    class FakeAgent:
        def supplement_cold_data(self, result, shop_id, date, reason):
            _ = (result, shop_id, reason)
            return {"dsr_trend": [{"date": date, "score": 4.7}]}

    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    monkeypatch.setattr(module, "LLMDashboardAgent", lambda: FakeAgent())
    monkeypatch.setattr(module, "_load_agent_context", _fake_load_agent_context)
    monkeypatch.setattr(module, "_persist_agent_patch", _fake_persist_agent_patch)
    monkeypatch.setattr(module, "datetime", _FrozenDatetime)

    result = module.sync_shop_dashboard_agent("shop-1", reason="cold_metric")

    assert result["status"] == "success"
    assert result["metric_date"] == "2026-03-04"
