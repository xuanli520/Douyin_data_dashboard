def test_register_jobs_contains_dashboard_full_incremental_cookie_agent(monkeypatch):
    from src.tasks import beat as module

    jobs: dict[str, dict] = {}

    class _FakeJobAdder:
        def __init__(self, _func, job_store_kind):
            _ = job_store_kind

        def add_push_job(self, **kwargs):
            jobs[kwargs["id"]] = kwargs

    monkeypatch.setattr(module, "ApsJobAdder", _FakeJobAdder)
    monkeypatch.setattr(
        module,
        "_load_active_shop_dashboard_rules",
        lambda: [
            {
                "rule_id": 2,
                "data_source_id": 1,
                "shop_id": "shop-1",
                "schedule": {"cron": "0 3 * * *"},
            }
        ],
    )

    module.register_jobs()

    assert "shop_dashboard_full_sync" in jobs
    assert "shop_dashboard_incremental_sync" in jobs
    assert "shop_dashboard_cookie_health_check" in jobs
    assert "shop_dashboard_agent_backfill" in jobs
    assert jobs["shop_dashboard_agent_backfill"]["kwargs"]["shop_id"] == "shop-1"
    assert "date" not in jobs["shop_dashboard_agent_backfill"]["kwargs"]


def test_register_jobs_skips_agent_backfill_without_shop_id(monkeypatch):
    from src.tasks import beat as module

    job_ids: list[str] = []

    class _FakeJobAdder:
        def __init__(self, _func, job_store_kind):
            _ = job_store_kind

        def add_push_job(self, **kwargs):
            job_ids.append(kwargs["id"])

    monkeypatch.setattr(module, "ApsJobAdder", _FakeJobAdder)
    monkeypatch.setattr(
        module,
        "_load_active_shop_dashboard_rules",
        lambda: [
            {
                "rule_id": 2,
                "data_source_id": 1,
                "shop_id": None,
                "schedule": {"cron": "0 3 * * *"},
            }
        ],
    )

    module.register_jobs()

    assert "shop_dashboard_agent_backfill" not in job_ids
