import pytest

from src.domains.collection_job.enums import CollectionJobStatus
from src.domains.collection_job.services import CollectionJobService
from src.domains.data_source.enums import DataSourceStatus, DataSourceType, TargetType
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.task.enums import TaskType
from src.exceptions import BusinessException


@pytest.mark.asyncio
async def test_collection_job_service_list_enabled_jobs(test_db):
    async with test_db() as session:
        data_source = DataSource(
            name="collection-job-data-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        session.add(data_source)
        await session.flush()

        rule = ScrapingRule(
            name="collection-job-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            target_type=TargetType.SHOP_OVERVIEW,
        )
        session.add(rule)
        await session.flush()

        service = CollectionJobService(session=session)
        await service.create_job(
            name="active-job",
            task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
            data_source_id=data_source.id if data_source.id is not None else 0,
            rule_id=rule.id if rule.id is not None else 0,
            schedule={"cron": "0 2 * * *", "kwargs": {"granularity": "DAY"}},
            status=CollectionJobStatus.ACTIVE,
        )
        await service.create_job(
            name="inactive-job",
            task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
            data_source_id=data_source.id if data_source.id is not None else 0,
            rule_id=rule.id if rule.id is not None else 0,
            schedule={"cron": "0 6 * * *"},
            status=CollectionJobStatus.INACTIVE,
        )

        jobs = await service.list_enabled_jobs(task_type="SHOP_DASHBOARD_COLLECTION")

    assert len(jobs) == 1
    assert jobs[0].status == CollectionJobStatus.ACTIVE
    assert jobs[0].schedule["cron"] == "0 2 * * *"
    assert jobs[0].schedule["timezone"] == "Asia/Shanghai"


@pytest.mark.asyncio
async def test_collection_job_service_create_job_validates_schedule(test_db):
    async with test_db() as session:
        data_source = DataSource(
            name="collection-job-invalid-schedule-data-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        session.add(data_source)
        await session.flush()

        rule = ScrapingRule(
            name="collection-job-invalid-schedule-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            target_type=TargetType.SHOP_OVERVIEW,
        )
        session.add(rule)
        await session.flush()

        service = CollectionJobService(session=session)

        with pytest.raises(BusinessException):
            await service.create_job(
                name="invalid-job",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=data_source.id if data_source.id is not None else 0,
                rule_id=rule.id if rule.id is not None else 0,
                schedule={"cron": "invalid"},
            )

        with pytest.raises(BusinessException):
            await service.create_job(
                name="invalid-job-7-fields",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=data_source.id if data_source.id is not None else 0,
                rule_id=rule.id if rule.id is not None else 0,
                schedule={"cron": "0 0 1 1 * 2026 1"},
            )
