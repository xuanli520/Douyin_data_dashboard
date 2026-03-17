from pathlib import Path
from types import SimpleNamespace

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


def test_register_jobs_removes_stale_collection_jobs(monkeypatch):
    from src.tasks import beat as module

    removed_ids: list[str] = []
    added_ids: list[str] = []
    existing_jobs = [
        SimpleNamespace(id="collection_job_1"),
        SimpleNamespace(id="collection_job_2"),
        SimpleNamespace(id="non_collection_job"),
    ]

    class _FakeAps:
        def get_jobs(self):
            return list(existing_jobs)

        def remove_job(self, job_id: str):
            removed_ids.append(job_id)

    class _FakeJobAdder:
        def __init__(self, _func, job_store_kind="redis"):
            _ = job_store_kind
            self.aps_obj = _FakeAps()

        def add_push_job(self, **kwargs):
            added_ids.append(kwargs["id"])

    monkeypatch.setattr(module, "ApsJobAdder", _FakeJobAdder)
    monkeypatch.setattr(
        module,
        "_load_enabled_collection_jobs",
        lambda: [
            CollectionJob(
                id=2,
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

    assert removed_ids == ["collection_job_1"]
    assert added_ids == ["collection_job_2"]


async def test_main_async_initializes_db_before_refresh_jobs(monkeypatch):
    from src.tasks import beat as module

    calls = []

    async def _fake_init_db(*_args, **_kwargs):
        calls.append("init_db")

    def _fake_configure_signal_handlers(stop_event):
        calls.append("configure_signal_handlers")
        stop_event.set()

    async def _fake_refresh_registered_jobs_async(*_args, **_kwargs):
        calls.append("refresh_jobs")
        return SimpleNamespace(id="scheduler")

    async def _fake_close_db():
        calls.append("close_db")

    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(
            db=SimpleNamespace(url="sqlite+aiosqlite:///beat-test.db", echo=False)
        ),
    )
    monkeypatch.setattr(module.session, "init_db", _fake_init_db)
    monkeypatch.setattr(
        module, "_configure_signal_handlers", _fake_configure_signal_handlers
    )
    monkeypatch.setattr(
        module,
        "_refresh_registered_jobs_async",
        _fake_refresh_registered_jobs_async,
    )
    monkeypatch.setattr(
        module, "_shutdown_scheduler", lambda _scheduler: calls.append("shutdown")
    )
    monkeypatch.setattr(module.session, "close_db", _fake_close_db)

    await module.main_async()

    assert calls[:3] == ["init_db", "configure_signal_handlers", "refresh_jobs"]


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


def test_no_legacy_fixed_rule_scheduler_branch():
    content = Path("src/tasks/beat.py").read_text(encoding="utf-8")
    assert "fixed_rule =" not in content
