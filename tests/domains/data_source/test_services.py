import pytest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.domains.data_source.enums import (
    DataSourceType as ModelDataSourceType,
    DataSourceStatus,
    TargetType,
)
from src.domains.data_source.schemas import (
    DataSourceCreate,
    DataSourceUpdate,
    DataSourceType,
    ScrapingRuleCreate,
    ScrapingRuleUpdate,
)
from src.domains.data_source.services import DataSourceService
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode

mock_session = AsyncMock()


class MockDataSource:
    def __init__(self, **kwargs):
        now = datetime.now(timezone.utc)
        self.id = kwargs.get("id", 1)
        self.name = kwargs.get("name", "Test DS")
        self.source_type = kwargs.get("source_type", ModelDataSourceType.DOUYIN_SHOP)
        self.status = kwargs.get("status", DataSourceStatus.ACTIVE)
        self.description = kwargs.get("description", None)
        self.extra_config = kwargs.get("extra_config", {})
        # Response schema fields
        self.type = kwargs.get("type", DataSourceType.DOUYIN_SHOP)
        self.config = kwargs.get("config", {})
        self.shop_id = kwargs.get("shop_id", None)
        self.rate_limit = kwargs.get("rate_limit", 100)
        self.retry_count = kwargs.get("retry_count", 3)
        self.timeout = kwargs.get("timeout", 30)
        self.last_used_at = kwargs.get("last_used_at", None)
        self.last_error_at = kwargs.get("last_error_at", None)
        self.last_error_msg = kwargs.get("last_error_msg", None)
        self.created_by_id = kwargs.get("created_by_id", 1)
        self.updated_by_id = kwargs.get("updated_by_id", 1)
        self.created_at = kwargs.get("created_at", now)
        self.updated_at = kwargs.get("updated_at", now)
        self.scraping_rules = kwargs.get("scraping_rules", [])


class MockScrapingRule:
    def __init__(self, **kwargs):
        now = datetime.now(timezone.utc)
        self.id = kwargs.get("id", 1)
        self.data_source_id = kwargs.get("data_source_id", 1)
        self.name = kwargs.get("name", "Test Rule")
        self.target_type = kwargs.get("target_type", TargetType.ORDER_FULFILLMENT)
        self.description = kwargs.get("description", None)
        self.schedule = kwargs.get("schedule", None)
        self.dimensions = kwargs.get("dimensions", None)
        self.metrics = kwargs.get("metrics", None)
        self.filters = kwargs.get("filters", None)
        self.granularity = kwargs.get("granularity", "DAY")
        self.timezone = kwargs.get("timezone", "Asia/Shanghai")
        self.incremental_mode = kwargs.get("incremental_mode", "BY_DATE")
        self.backfill_last_n_days = kwargs.get("backfill_last_n_days", 3)
        self.data_latency = kwargs.get("data_latency", "T+1")
        self.dedupe_key = kwargs.get("dedupe_key", None)
        self.top_n = kwargs.get("top_n", None)
        self.sort_by = kwargs.get("sort_by", None)
        self.include_long_tail = kwargs.get("include_long_tail", False)
        self.session_level = kwargs.get("session_level", False)
        self.status = kwargs.get("status", "ACTIVE")
        # Response schema fields
        self.rule_type = kwargs.get("rule_type", TargetType.ORDER_FULFILLMENT)
        self.config = kwargs.get("config", {})
        self.is_active = kwargs.get("is_active", True)
        self.last_executed_at = kwargs.get("last_executed_at", None)
        self.last_execution_id = kwargs.get("last_execution_id", None)
        self.created_at = kwargs.get("created_at", now)
        self.updated_at = kwargs.get("updated_at", now)


@pytest.mark.asyncio
class TestDataSourceServiceUnit:
    async def test_create_data_source_success(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.create.return_value = MockDataSource(
            id=1,
            name="Test DS",
            source_type=ModelDataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
            description="Test description",
            extra_config={"api_key": "test_key"},
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        data = DataSourceCreate(
            name="Test DS",
            type=DataSourceType.DOUYIN_SHOP,
            config={"api_key": "test_key", "api_key_password": "test_secret"},
            description="Test description",
        )

        result = await service.create(data, user_id=1)

        assert result.name == "Test DS"
        mock_ds_repo.create.assert_called_once()

    async def test_create_data_source_without_api_credentials(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()
        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)

        data = DataSourceCreate(
            name="Test DS",
            type=DataSourceType.DOUYIN_SHOP,
            config={},
        )

        mock_ds_repo.create.return_value = MockDataSource(
            id=1,
            name="Test DS",
            source_type=ModelDataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
            description=None,
            extra_config={},
        )

        result = await service.create(data, user_id=1)

        assert result.name == "Test DS"
        mock_ds_repo.create.assert_called_once()

    async def test_get_by_id_success(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            name="Test DS",
            scraping_rules=[],
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        result = await service.get_by_id(1)

        assert result.id == 1
        assert result.name == "Test DS"

    async def test_get_by_id_not_found(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()
        mock_ds_repo.get_by_id.return_value = None

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)

        with pytest.raises(BusinessException) as exc_info:
            await service.get_by_id(999)
        assert exc_info.value.code == ErrorCode.DATASOURCE_NOT_FOUND

    async def test_list_paginated(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_paginated.return_value = (
            [MockDataSource(id=1, name="Test DS")],
            1,
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        result, total = await service.list_paginated(page=1, size=10)

        assert len(result) == 1
        assert total == 1
        mock_ds_repo.get_paginated.assert_called_once()

    async def test_update_success(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            name="Original Name",
            description="Original Desc",
        )

        mock_ds_repo.update.return_value = MockDataSource(
            id=1,
            name="Updated Name",
            description="Updated Desc",
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        data = DataSourceUpdate(name="Updated Name", description="Updated Desc")
        result = await service.update(1, data, user_id=1)

        assert result.name == "Updated Name"

    async def test_update_not_found(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()
        mock_ds_repo.get_by_id.return_value = None

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)

        with pytest.raises(BusinessException) as exc_info:
            await service.update(999, DataSourceUpdate(name="New Name"), user_id=1)
        assert exc_info.value.code == ErrorCode.DATASOURCE_NOT_FOUND

    async def test_update_shop_dashboard_login_state_returns_masked_response(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            source_type=ModelDataSourceType.DOUYIN_SHOP,
            extra_config={
                "shop_dashboard_login_state": {
                    "credentials": {
                        "api_key": "key",
                        "api_key_password": "password",
                    }
                }
            },
        )
        mock_ds_repo.update.return_value = MockDataSource(
            id=1,
            source_type=ModelDataSourceType.DOUYIN_SHOP,
            extra_config={
                "shop_dashboard_login_state": {
                    "credentials": {
                        "api_key": "key",
                        "api_key_password": "password",
                    },
                    "storage_state": {
                        "cookies": [{"name": "sid", "value": "token"}],
                        "origins": [],
                    },
                    "state_version": "v1",
                },
                "shop_dashboard_login_state_meta": {
                    "account_id": "acct-1",
                    "cookie_count": 1,
                    "state_version": "v1",
                },
            },
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        result = await service.update_shop_dashboard_login_state(
            1,
            account_id="acct-1",
            storage_state={
                "cookies": [{"name": "sid", "value": "token"}],
                "origins": [],
            },
            user_id=1,
        )

        assert result.config["shop_dashboard_login_state_meta"]["cookie_count"] == 1
        assert "shop_dashboard_login_state" not in result.config

        update_payload = mock_ds_repo.update.await_args.args[1]
        saved_login_state = update_payload["extra_config"]["shop_dashboard_login_state"]
        assert isinstance(saved_login_state["storage_state"], dict)
        assert saved_login_state["storage_state"]["cookies"][0]["name"] == "sid"
        assert "cookies" not in saved_login_state

    async def test_clear_shop_dashboard_login_state_removes_raw_and_meta(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            source_type=ModelDataSourceType.DOUYIN_SHOP,
            extra_config={
                "shop_dashboard_login_state": {"cookies": [], "origins": []},
                "shop_dashboard_login_state_meta": {
                    "account_id": "acct-1",
                    "cookie_count": 0,
                    "state_version": "v1",
                },
            },
        )
        mock_ds_repo.update.return_value = MockDataSource(
            id=1,
            source_type=ModelDataSourceType.DOUYIN_SHOP,
            extra_config={},
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        result = await service.clear_shop_dashboard_login_state(1, user_id=1)

        assert "shop_dashboard_login_state" not in result.config
        assert "shop_dashboard_login_state_meta" not in result.config

    async def test_delete_success(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        await service.delete(1)

        mock_ds_repo.delete.assert_called_once_with(1)

    async def test_activate_success(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            status=DataSourceStatus.INACTIVE,
        )

        mock_ds_repo.update.return_value = MockDataSource(
            id=1,
            status=DataSourceStatus.ACTIVE,
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        result = await service.activate(1, user_id=1)

        assert result.status == DataSourceStatus.ACTIVE

    async def test_activate_already_active(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            status=DataSourceStatus.ACTIVE,
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)

        with pytest.raises(BusinessException) as exc_info:
            await service.activate(1, user_id=1)
        assert exc_info.value.code == ErrorCode.DATASOURCE_ALREADY_ACTIVE

    async def test_deactivate_success(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            status=DataSourceStatus.ACTIVE,
        )

        mock_ds_repo.update.return_value = MockDataSource(
            id=1,
            status=DataSourceStatus.INACTIVE,
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        result = await service.deactivate(1, user_id=1)

        assert result.status == DataSourceStatus.INACTIVE

    async def test_deactivate_already_inactive(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            status=DataSourceStatus.INACTIVE,
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)

        with pytest.raises(BusinessException) as exc_info:
            await service.deactivate(1, user_id=1)
        assert exc_info.value.code == ErrorCode.DATASOURCE_ALREADY_INACTIVE

    async def test_validate_connection_success(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            source_type=ModelDataSourceType.DOUYIN_SHOP,
            extra_config={
                "shop_dashboard_login_state": {
                    "credentials": {
                        "api_key": "test_key",
                        "api_key_password": "test_secret",
                    }
                }
            },
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        result = await service.validate_connection(1)

        assert result["valid"] is True
        mock_ds_repo.update_last_used.assert_called_once_with(1)

    async def test_validate_connection_failure(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            source_type=ModelDataSourceType.DOUYIN_SHOP,
            extra_config={},
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        result = await service.validate_connection(1)

        assert result["valid"] is False
        mock_ds_repo.record_error.assert_called_once()

    async def test_create_scraping_rule_success(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            status=DataSourceStatus.ACTIVE,
        )

        mock_rule_repo.create.return_value = MockScrapingRule(
            id=1,
            data_source_id=1,
            name="Test Rule",
            target_type=TargetType.ORDER_FULFILLMENT,
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        data = ScrapingRuleCreate(
            data_source_id=1,
            name="Test Rule",
            target_type=TargetType.ORDER_FULFILLMENT,
        )
        result = await service.create_scraping_rule(1, data)

        assert result.name == "Test Rule"

    async def test_create_scraping_rule_inactive_source(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            status=DataSourceStatus.INACTIVE,
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        data = ScrapingRuleCreate(
            data_source_id=1,
            name="Test Rule",
            target_type=TargetType.ORDER_FULFILLMENT,
        )

        with pytest.raises(BusinessException) as exc_info:
            await service.create_scraping_rule(1, data)
        assert exc_info.value.code == ErrorCode.DATA_VALIDATION_FAILED

    async def test_list_scraping_rules(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(id=1)

        mock_rule_repo.get_by_data_source.return_value = [
            MockScrapingRule(
                id=1,
                data_source_id=1,
                name="Rule 1",
                target_type=TargetType.ORDER_FULFILLMENT,
            )
        ]

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        result = await service.list_scraping_rules(1)

        assert len(result) == 1
        assert result[0].name == "Rule 1"

    async def test_update_scraping_rule_success(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_rule_repo.get_by_id.return_value = MockScrapingRule(
            id=1,
            data_source_id=1,
            name="Updated Rule",
            target_type=TargetType.ORDER_FULFILLMENT,
        )
        mock_rule_repo.update.return_value = MockScrapingRule(
            id=1,
            data_source_id=1,
            name="Updated Rule",
            target_type=TargetType.ORDER_FULFILLMENT,
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        data = ScrapingRuleUpdate(name="Updated Rule")
        result = await service.update_scraping_rule(1, data)

        assert result.name == "Updated Rule"

    async def test_delete_scraping_rule(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        await service.delete_scraping_rule(1)

        mock_rule_repo.delete.assert_called_once_with(1)

    async def test_trigger_collection_success(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            status=DataSourceStatus.ACTIVE,
            scraping_rules=[MockScrapingRule(id=1, name="Test Rule")],
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        service._push_shop_dashboard_task = AsyncMock(
            return_value=SimpleNamespace(task_id="task-1")
        )
        result = await service.trigger_collection(1)

        assert result["total"] == 1
        assert len(result["triggered_rules"]) == 1
        assert result["triggered_rules"][0]["task_id"] == "task-1"
        assert result["triggered_rules"][0]["status"] == "queued"
        mock_rule_repo.update.assert_awaited()

    async def test_trigger_collection_inactive_source(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            status=DataSourceStatus.INACTIVE,
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)

        with pytest.raises(BusinessException) as exc_info:
            await service.trigger_collection(1)
        assert exc_info.value.code == ErrorCode.DATA_VALIDATION_FAILED

    async def test_trigger_collection_specific_rule(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            status=DataSourceStatus.ACTIVE,
            scraping_rules=[
                MockScrapingRule(id=1, name="Rule 1"),
                MockScrapingRule(id=2, name="Rule 2"),
            ],
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)
        service._push_shop_dashboard_task = AsyncMock(
            return_value=SimpleNamespace(task_id="task-1")
        )
        result = await service.trigger_collection(1, rule_id=1)

        assert result["total"] == 1
        assert result["triggered_rules"][0]["rule_id"] == 1
        assert result["triggered_rules"][0]["task_id"] == "task-1"

    async def test_trigger_collection_rule_not_found(self):
        mock_ds_repo = AsyncMock()
        mock_rule_repo = AsyncMock()

        mock_ds_repo.get_by_id.return_value = MockDataSource(
            id=1,
            status=DataSourceStatus.ACTIVE,
            scraping_rules=[MockScrapingRule(id=1, name="Rule 1")],
        )

        service = DataSourceService(mock_ds_repo, mock_rule_repo, mock_session)

        with pytest.raises(BusinessException) as exc_info:
            await service.trigger_collection(1, rule_id=999)
        assert exc_info.value.code == ErrorCode.SCRAPING_RULE_NOT_FOUND
