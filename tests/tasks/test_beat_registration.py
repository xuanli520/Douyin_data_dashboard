import pytest
from sqlalchemy import text

from src.domains.collection_job.enums import CollectionJobStatus
from src.domains.collection_job.models import CollectionJob
from src.domains.data_source.enums import DataSourceStatus, DataSourceType, TargetType
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.task.enums import TaskType


def test_register_jobs_uses_collection_job_ids(monkeypatch):
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
        "_load_enabled_collection_jobs",
        lambda: [
            CollectionJob(
                id=99,
                name="beat-registration-job",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=11,
                rule_id=12,
                schedule={"cron": "0 2 * * *"},
                status=CollectionJobStatus.ACTIVE,
            )
        ],
        raising=False,
    )

    module.register_jobs()

    add_ids = [item[1] for item in calls if item[0] == "add"]
    assert add_ids == ["collection_job_99"]
    assert "shop_dashboard_full_sync" not in add_ids


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


async def test_load_enabled_collection_jobs_async_excludes_inactive_jobs(
    test_db, monkeypatch
):
    from src.tasks import beat as module

    async with test_db() as db_session:
        data_source = DataSource(
            name="beat-registration-active-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        db_session.add(data_source)
        await db_session.flush()

        rule = ScrapingRule(
            name="beat-registration-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            target_type=TargetType.SHOP_OVERVIEW,
        )
        db_session.add(rule)
        await db_session.flush()

        db_session.add(
            CollectionJob(
                name="beat-registration-job-active",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=data_source.id if data_source.id is not None else 0,
                rule_id=rule.id if rule.id is not None else 0,
                schedule={"cron": "0 2 * * *"},
                status=CollectionJobStatus.ACTIVE,
            )
        )
        db_session.add(
            CollectionJob(
                name="beat-registration-job-inactive",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=data_source.id if data_source.id is not None else 0,
                rule_id=rule.id if rule.id is not None else 0,
                schedule={"cron": "0 6 * * *"},
                status=CollectionJobStatus.INACTIVE,
            )
        )
        await db_session.commit()

    monkeypatch.setattr(module.session, "async_session_factory", test_db, raising=False)
    jobs = await module._load_enabled_collection_jobs_async()

    assert len(jobs) == 1
    assert jobs[0].name == "beat-registration-job-active"


async def test_load_enabled_collection_jobs_async_requires_collection_jobs_table(
    test_db, monkeypatch
):
    from src.tasks import beat as module

    async with test_db() as db_session:
        await db_session.execute(text("DROP TABLE collection_jobs"))
        await db_session.commit()

    monkeypatch.setattr(module.session, "async_session_factory", test_db, raising=False)

    with pytest.raises(RuntimeError):
        await module._load_enabled_collection_jobs_async()
