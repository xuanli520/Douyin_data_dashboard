from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.domains.collection_job.enums import CollectionJobStatus
from src.domains.collection_job.models import CollectionJob
from src.domains.data_source.enums import (
    DataSourceStatus,
    DataSourceType,
    ScrapingRuleStatus,
    TargetType,
)
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.scraping_rule.schemas import ScrapingRuleUpdate
from src.domains.scraping_rule.services import ScrapingRuleService
from src.domains.task.enums import TaskExecutionStatus
from src.domains.task.enums import TaskType
from src.domains.task.models import TaskDefinition, TaskExecution
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


@pytest.mark.asyncio
async def test_scraping_rule_service_create_rule(test_db):
    async with test_db() as session:
        data_source = DataSource(
            name="ds-1",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        session.add(data_source)
        await session.commit()
        await session.refresh(data_source)

        service = ScrapingRuleService(session=session)
        created = await service.create_rule(
            data_source_id=data_source.id if data_source.id is not None else 0,
            name="rule-a",
            target_type=TargetType.SHOP_OVERVIEW,
            config={"granularity": "DAY"},
            description=None,
        )

        assert created.id > 0
        assert created.version == 1


@pytest.mark.asyncio
async def test_scraping_rule_service_create_rule_inactive_data_source():
    session = AsyncMock()
    service = ScrapingRuleService(session=session)
    service.ds_repo = AsyncMock()
    service.rule_repo = AsyncMock()
    service.ds_repo.get_by_id.return_value = SimpleNamespace(
        id=1,
        status=DataSourceStatus.INACTIVE,
    )

    with pytest.raises(BusinessException) as exc:
        await service.create_rule(
            data_source_id=1,
            name="rule-a",
            target_type=TargetType.SHOP_OVERVIEW,
            config={},
            description=None,
        )

    assert exc.value.code == ErrorCode.DATA_VALIDATION_FAILED


@pytest.mark.asyncio
async def test_scraping_rule_service_update_rule_should_increment_version():
    session = AsyncMock()
    service = ScrapingRuleService(session=session)
    service.rule_repo = AsyncMock()
    service.ds_repo = AsyncMock()

    rule = SimpleNamespace(
        id=1,
        data_source_id=1,
        name="rule-a",
        target_type=TargetType.SHOP_OVERVIEW,
        description=None,
        status=ScrapingRuleStatus.ACTIVE,
        version=1,
        granularity="DAY",
        timezone="Asia/Shanghai",
        time_range=None,
        incremental_mode="BY_DATE",
        backfill_last_n_days=3,
        filters=None,
        dimensions=None,
        metrics=None,
        dedupe_key=None,
        rate_limit=None,
        data_latency="T+1",
        top_n=None,
        sort_by=None,
        include_long_tail=False,
        session_level=False,
        last_executed_at=None,
        last_execution_id=None,
        extra_config=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        data_source=None,
    )
    service.rule_repo.get_by_id.return_value = rule
    updated_rule_data = dict(rule.__dict__)
    updated_rule_data["name"] = "rule-b"
    updated_rule_data["version"] = 2
    service.rule_repo.update.return_value = SimpleNamespace(**updated_rule_data)

    result = await service.update_rule(
        1,
        ScrapingRuleUpdate(name="rule-b", config={"granularity": "WEEK"}),
    )

    assert result.version == 2
    update_payload = service.rule_repo.update.await_args.args[1]
    assert update_payload["version"] == 2


def test_scraping_rule_service_should_not_expose_trigger_collection():
    assert not hasattr(ScrapingRuleService, "trigger_collection")


@pytest.mark.asyncio
async def test_list_rules_paginated_should_not_expose_schedule_summary(test_db):
    async with test_db() as session:
        data_source = DataSource(
            name="ds-schedule",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        session.add(data_source)
        await session.flush()

        rule = ScrapingRule(
            name="rule-with-schedule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            target_type=TargetType.SHOP_OVERVIEW,
        )
        session.add(rule)
        await session.flush()

        session.add_all(
            [
                CollectionJob(
                    name="full-sync",
                    task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                    data_source_id=data_source.id if data_source.id is not None else 0,
                    rule_id=rule.id if rule.id is not None else 0,
                    schedule={"cron": "0 2 * * *", "timezone": "Asia/Shanghai"},
                    status=CollectionJobStatus.ACTIVE,
                ),
                CollectionJob(
                    name="incremental-sync",
                    task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                    data_source_id=data_source.id if data_source.id is not None else 0,
                    rule_id=rule.id if rule.id is not None else 0,
                    schedule={
                        "cron": "0 6,10,14,18 * * *",
                        "timezone": "Asia/Shanghai",
                    },
                    status=CollectionJobStatus.ACTIVE,
                ),
            ]
        )
        await session.commit()

        service = ScrapingRuleService(session=session)
        rules, total = await service.list_rules_paginated(page=1, size=10)

        assert total == 1
        assert "schedule" not in rules[0].model_dump()


@pytest.mark.asyncio
async def test_list_rules_by_data_source_should_not_expose_schedule_and_should_keep_last_run_fallback(
    test_db,
):
    async with test_db() as session:
        data_source = DataSource(
            name="ds-last-run-fallback",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        session.add(data_source)
        await session.flush()

        rule = ScrapingRule(
            name="rule-last-run-fallback",
            data_source_id=data_source.id if data_source.id is not None else 0,
            target_type=TargetType.SHOP_OVERVIEW,
            last_executed_at=None,
            last_execution_id=None,
        )
        session.add(rule)
        await session.flush()

        task = TaskDefinition(
            name="shop_dashboard_collection",
            task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
        )
        session.add(task)
        await session.flush()

        session.add(
            CollectionJob(
                name="fallback-sync",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
                data_source_id=data_source.id if data_source.id is not None else 0,
                rule_id=rule.id if rule.id is not None else 0,
                schedule={"cron": "0 8 * * *", "timezone": "Asia/Shanghai"},
                status=CollectionJobStatus.ACTIVE,
            )
        )
        session.add(
            TaskExecution(
                task_id=task.id if task.id is not None else 0,
                queue_task_id="queue-last-run-fallback",
                status=TaskExecutionStatus.SUCCESS,
                payload={
                    "data_source_id": data_source.id
                    if data_source.id is not None
                    else 0,
                    "rule_id": rule.id if rule.id is not None else 0,
                    "execution_id": "exec-last-run-fallback",
                    "overrides": {},
                },
                completed_at=datetime(2026, 3, 17, 8, 0, tzinfo=timezone.utc),
            )
        )
        await session.commit()

        service = ScrapingRuleService(session=session)
        rules = await service.list_rules_by_data_source(
            data_source.id if data_source.id is not None else 0
        )

        assert len(rules) == 1
        assert "schedule" not in rules[0].model_dump()
        assert rules[0].last_executed_at is not None
        assert rules[0].last_executed_at.isoformat().startswith("2026-03-17T08:00:00")
        assert rules[0].last_execution_id == "exec-last-run-fallback"
