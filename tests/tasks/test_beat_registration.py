def test_register_jobs_uses_fixed_ids(monkeypatch):
    from src.tasks import beat as module

    calls = []

    class _FakeJobAdder:
        def __init__(self, func, job_store_kind):
            calls.append(("init", getattr(func, "__name__", str(func)), job_store_kind))

        def add_push_job(self, **kwargs):
            calls.append(("add", kwargs["id"], kwargs["trigger"]))

    monkeypatch.setattr(module, "ApsJobAdder", _FakeJobAdder)
    monkeypatch.setattr(
        module,
        "_load_active_shop_dashboard_rules",
        lambda: [
            {
                "rule_id": 99,
                "data_source_id": 11,
                "schedule": {"cron": "0 3 * * *"},
            }
        ],
        raising=False,
    )
    module.register_jobs()

    add_ids = [item[1] for item in calls if item[0] == "add"]
    assert "scraping_rule_99_collection_shop_dashboard_sync" in add_ids


def test_main_initializes_db_before_register_jobs(monkeypatch):
    from src.tasks import beat as module

    calls = []
    monkeypatch.setattr(module, "_init_scheduler_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(module, "register_jobs", lambda: calls.append("register_jobs"))

    def _stop_loop(_seconds):
        raise RuntimeError("stop-loop")

    monkeypatch.setattr(module.time, "sleep", _stop_loop)

    try:
        module.main()
    except RuntimeError as exc:
        assert str(exc) == "stop-loop"

    assert calls[:2] == ["init_db", "register_jobs"]


async def test_load_active_shop_dashboard_rules_excludes_inactive_data_source(
    test_db, monkeypatch
):
    from src.domains.data_source.enums import (
        DataSourceStatus,
        DataSourceType,
        ScrapingRuleStatus,
    )
    from src.domains.data_source.models import DataSource, ScrapingRule
    from src.tasks import beat as module

    async with test_db() as db_session:
        active_source = DataSource(
            name="active-shop-dashboard-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        inactive_source = DataSource(
            name="inactive-shop-dashboard-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.INACTIVE,
        )
        db_session.add(active_source)
        db_session.add(inactive_source)
        await db_session.flush()

        active_rule = ScrapingRule(
            name="active-shop-dashboard-rule",
            data_source_id=active_source.id if active_source.id is not None else 0,
            status=ScrapingRuleStatus.ACTIVE,
            schedule={"cron": "0 3 * * *"},
        )
        inactive_source_rule = ScrapingRule(
            name="inactive-source-shop-dashboard-rule",
            data_source_id=inactive_source.id if inactive_source.id is not None else 0,
            status=ScrapingRuleStatus.ACTIVE,
            schedule={"cron": "0 4 * * *"},
        )
        db_session.add(active_rule)
        db_session.add(inactive_source_rule)
        await db_session.commit()

    monkeypatch.setattr(module.session, "async_session_factory", test_db, raising=False)
    rules = await module._load_active_shop_dashboard_rules_async()

    rule_ids = {item["rule_id"] for item in rules}
    assert active_rule.id in rule_ids
    assert inactive_source_rule.id not in rule_ids
