from src.domains.collection_job.enums import CollectionJobStatus
from src.domains.collection_job.models import CollectionJob
from src.domains.data_source.enums import DataSourceStatus, DataSourceType, TargetType
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.task.enums import TaskType


def test_register_jobs_groups_by_task_type_and_reuses_single_adder(monkeypatch):
    from src.tasks import beat as module

    init_calls: list[tuple[str, str]] = []
    added_jobs: list[dict] = []

    class _FakeJobAdder:
        def __init__(self, task_func, job_store_kind):
            init_calls.append(
                (getattr(task_func, "__name__", str(task_func)), job_store_kind)
            )

        def add_push_job(self, **kwargs):
            added_jobs.append(kwargs)

    monkeypatch.setattr(module, "ApsJobAdder", _FakeJobAdder)
    monkeypatch.setattr(
        module,
        "_load_enabled_collection_jobs",
        lambda: [
            CollectionJob(
                id=1,
                name="shop-job-1",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=10,
                rule_id=100,
                schedule={
                    "cron": "0 2 * * *",
                    "kwargs": {
                        "shop_id": "shop-1",
                        "all": True,
                        "unexpected": "drop",
                    },
                },
                status=CollectionJobStatus.ACTIVE,
            ),
            CollectionJob(
                id=2,
                name="shop-job-2",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=11,
                rule_id=101,
                schedule={"cron": "0 */6 * * *"},
                status=CollectionJobStatus.ACTIVE,
            ),
            CollectionJob(
                id=3,
                name="orders-job",
                task_type=TaskType.ETL_ORDERS,
                data_source_id=10,
                rule_id=100,
                schedule={
                    "cron": "0 9 * * *",
                    "kwargs": {"batch_date": "2026-03-10"},
                },
                status=CollectionJobStatus.ACTIVE,
            ),
        ],
    )

    module.register_jobs()

    assert len(init_calls) == 2
    assert ("sync_shop_dashboard", "redis") in init_calls
    assert ("process_orders", "redis") in init_calls
    assert {item["id"] for item in added_jobs} == {
        "collection_job_1",
        "collection_job_2",
        "collection_job_3",
    }

    first_shop_job = next(
        item for item in added_jobs if item["id"] == "collection_job_1"
    )
    second_shop_job = next(
        item for item in added_jobs if item["id"] == "collection_job_2"
    )
    orders_job = next(item for item in added_jobs if item["id"] == "collection_job_3")

    assert first_shop_job["kwargs"] == {
        "data_source_id": 10,
        "rule_id": 100,
        "execution_id": "cron_collection_job_1",
        "triggered_by": None,
        "shop_id": "shop-1",
        "all": True,
    }
    assert second_shop_job["kwargs"] == {
        "data_source_id": 11,
        "rule_id": 101,
        "execution_id": "cron_collection_job_2",
        "triggered_by": None,
    }
    assert orders_job["kwargs"] == {
        "triggered_by": None,
        "execution_id": "cron_collection_job_3",
        "batch_date": "2026-03-10",
    }


async def test_load_enabled_collection_jobs_async_returns_only_active_jobs(
    test_db, monkeypatch
):
    from src.tasks import beat as module

    async with test_db() as session:
        data_source = DataSource(
            name="beat-active-data-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        session.add(data_source)
        await session.flush()

        rule = ScrapingRule(
            name="beat-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            target_type=TargetType.SHOP_OVERVIEW,
        )
        session.add(rule)
        await session.flush()

        session.add(
            CollectionJob(
                name="beat-job-active",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=data_source.id if data_source.id is not None else 0,
                rule_id=rule.id if rule.id is not None else 0,
                schedule={"cron": "0 2 * * *"},
                status=CollectionJobStatus.ACTIVE,
            )
        )
        session.add(
            CollectionJob(
                name="beat-job-inactive",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=data_source.id if data_source.id is not None else 0,
                rule_id=rule.id if rule.id is not None else 0,
                schedule={"cron": "0 6 * * *"},
                status=CollectionJobStatus.INACTIVE,
            )
        )
        await session.commit()

    monkeypatch.setattr(module.session, "async_session_factory", test_db, raising=False)

    jobs = await module._load_enabled_collection_jobs_async()

    assert len(jobs) == 1
    assert jobs[0].name == "beat-job-active"
    assert jobs[0].status == CollectionJobStatus.ACTIVE
