import pytest

from src.domains.data_source.enums import DataSourceStatus, TargetType
from src.domains.data_source.repository import (
    DataSourceRepository,
    ScrapingRuleRepository,
)
from src.domains.data_source.schemas import (
    DataSourceCreate,
    DataSourceUpdate,
    ScrapingRuleCreate,
    ScrapingRuleUpdate,
    DataSourceType as SchemaDataSourceType,
)
from src.domains.data_source.services import DataSourceService
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


@pytest.mark.asyncio
class TestDataSourceServiceIntegration:
    async def test_create_and_get_data_source(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            data = DataSourceCreate(
                name="Integration Test DS",
                type=SchemaDataSourceType.DOUYIN_SHOP,
                config={"api_key": "test_key", "api_secret": "test_secret"},
                description="Test description",
            )
            created = await service.create(data, user_id=test_user.id)

            assert created.id is not None
            assert created.name == "Integration Test DS"

            fetched = await service.get_by_id(created.id)
            assert fetched.id == created.id
            assert fetched.name == "Integration Test DS"

    async def test_create_shop_dashboard_config_merges_credentials_into_login_state(
        self, test_db, test_user
    ):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            created = await service.create(
                DataSourceCreate(
                    name="Shop DS Credential Merge",
                    type=SchemaDataSourceType.DOUYIN_SHOP,
                    config={
                        "api_key": "test_key",
                        "api_key_password": "test_password",
                        "shop_id": "shop-1",
                    },
                ),
                user_id=test_user.id,
            )

            model = await ds_repo.get_by_id(created.id)
            assert model is not None
            login_state = model.extra_config.get("shop_dashboard_login_state")
            assert login_state["credentials"]["api_key"] == "test_key"
            assert login_state["credentials"]["api_key_password"] == "test_password"
            assert "shop_dashboard_login_state" not in created.config

    async def test_update_and_clear_shop_dashboard_login_state(
        self, test_db, test_user
    ):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            created = await service.create(
                DataSourceCreate(
                    name="Shop DS Login State",
                    type=SchemaDataSourceType.DOUYIN_SHOP,
                    config={
                        "api_key": "test_key",
                        "api_key_password": "test_password",
                    },
                ),
                user_id=test_user.id,
            )

            updated = await service.update_shop_dashboard_login_state(
                created.id,
                account_id="acct-1",
                storage_state={
                    "cookies": [{"name": "sid", "value": "token"}],
                    "origins": [],
                },
                user_id=test_user.id,
            )
            assert (
                updated.config["shop_dashboard_login_state_meta"]["cookie_count"] == 1
            )
            assert "shop_dashboard_login_state" not in updated.config

            model = await ds_repo.get_by_id(created.id)
            assert model is not None
            login_state = model.extra_config["shop_dashboard_login_state"]
            assert isinstance(login_state.get("storage_state"), dict)
            assert login_state["storage_state"]["cookies"][0]["name"] == "sid"
            assert "cookies" not in login_state

            cleared = await service.clear_shop_dashboard_login_state(
                created.id,
                user_id=test_user.id,
            )
            assert "shop_dashboard_login_state" not in cleared.config
            assert "shop_dashboard_login_state_meta" not in cleared.config

    @pytest.mark.skip(reason="Requires PostgreSQL for unique constraint error handling")
    async def test_create_duplicate_name_raises_error(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            data = DataSourceCreate(
                name="Duplicate Name",
                type=SchemaDataSourceType.DOUYIN_SHOP,
                config={"api_key": "key1", "api_secret": "secret1"},
            )
            await service.create(data, user_id=test_user.id)

            with pytest.raises(BusinessException) as exc_info:
                await service.create(data, user_id=test_user.id)
            assert exc_info.value.code == ErrorCode.DATASOURCE_NAME_CONFLICT

    async def test_list_paginated_with_filters(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            for i in range(5):
                await service.create(
                    DataSourceCreate(
                        name=f"DS {i}",
                        type=SchemaDataSourceType.DOUYIN_SHOP,
                        config={"api_key": f"key_{i}", "api_secret": f"secret_{i}"},
                        status=DataSourceStatus.ACTIVE
                        if i % 2 == 0
                        else DataSourceStatus.INACTIVE,
                    ),
                    user_id=test_user.id,
                )

            items, total = await service.list_paginated(page=1, size=10)
            assert total == 5
            assert len(items) == 5

            active_items, total_active = await service.list_paginated(
                page=1, size=10, status=DataSourceStatus.ACTIVE
            )
            assert total_active == 3

            named_items, total_named = await service.list_paginated(
                page=1, size=10, name="DS 1"
            )
            assert total_named == 1
            assert named_items[0].name == "DS 1"

    async def test_update_data_source(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            created = await service.create(
                DataSourceCreate(
                    name="Original Name",
                    type=SchemaDataSourceType.DOUYIN_API,
                    config={"api_key": "key", "api_secret": "secret"},
                ),
                user_id=test_user.id,
            )

            updated = await service.update(
                created.id,
                DataSourceUpdate(name="Updated Name", description="Updated Desc"),
                user_id=test_user.id,
            )

            assert updated.name == "Updated Name"

            fetched = await service.get_by_id(created.id)
            assert fetched.name == "Updated Name"

    async def test_delete_data_source(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            created = await service.create(
                DataSourceCreate(
                    name="To Delete",
                    type=SchemaDataSourceType.DOUYIN_SHOP,
                    config={"api_key": "key", "api_secret": "secret"},
                ),
                user_id=test_user.id,
            )

            await service.delete(created.id)

            with pytest.raises(BusinessException) as exc_info:
                await service.get_by_id(created.id)
            assert exc_info.value.code == ErrorCode.DATASOURCE_NOT_FOUND

    async def test_activate_deactivate_data_source(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            created = await service.create(
                DataSourceCreate(
                    name="Status Test",
                    type=SchemaDataSourceType.DOUYIN_SHOP,
                    config={"api_key": "key", "api_secret": "secret"},
                    status=DataSourceStatus.ACTIVE,
                ),
                user_id=test_user.id,
            )
            assert created.status == DataSourceStatus.ACTIVE

            deactivated = await service.deactivate(created.id, user_id=test_user.id)
            assert deactivated.status == DataSourceStatus.INACTIVE

            activated = await service.activate(created.id, user_id=test_user.id)
            assert activated.status == DataSourceStatus.ACTIVE

    async def test_validate_connection(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            created = await service.create(
                DataSourceCreate(
                    name="Connection Test",
                    type=SchemaDataSourceType.DOUYIN_SHOP,
                    config={
                        "shop_dashboard_login_state": {
                            "storage_state": {
                                "cookies": [{"name": "sid", "value": "token"}],
                                "origins": [],
                            }
                        }
                    },
                ),
                user_id=test_user.id,
            )

            result = await service.validate_connection(created.id)
            assert result["valid"] is True

            fetched = await ds_repo.get_by_id(created.id)
            assert fetched.last_used_at is not None

    async def test_validate_connection_failure(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            created = await service.create(
                DataSourceCreate(
                    name="Connection Fail Test",
                    type=SchemaDataSourceType.DOUYIN_SHOP,
                    config={"api_key": "valid_key", "api_secret": "valid_secret"},
                ),
                user_id=test_user.id,
            )
            await ds_repo.update(created.id, {"extra_config": {}})

            result = await service.validate_connection(created.id)
            assert result["valid"] is False
            assert result["message"] == "Missing shop dashboard login state cookies"

            fetched = await ds_repo.get_by_id(created.id)
            assert fetched.status == DataSourceStatus.ERROR
            assert fetched.last_error_msg is not None


@pytest.mark.asyncio
class TestScrapingRuleServiceIntegration:
    async def test_create_scraping_rule(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            ds = await service.create(
                DataSourceCreate(
                    name="DS for Rules",
                    type=SchemaDataSourceType.DOUYIN_API,
                    config={"api_key": "key", "api_secret": "secret"},
                ),
                user_id=test_user.id,
            )

            rule_data = ScrapingRuleCreate(
                data_source_id=ds.id,
                name="Test Rule",
                target_type=TargetType.ORDER_FULFILLMENT,
                config={"max_orders": 100},
            )
            rule = await service.create_scraping_rule(ds.id, rule_data)

            assert rule.id is not None
            assert rule.name == "Test Rule"

    async def test_create_scraping_rule_with_full_rule_config_and_shop_id_list(
        self, test_db, test_user
    ):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            ds = await service.create(
                DataSourceCreate(
                    name="DS for Full Rule Config",
                    type=SchemaDataSourceType.DOUYIN_SHOP,
                    config={"shop_id": None},
                ),
                user_id=test_user.id,
            )
            shop_ids = [f"shop-{idx}" for idx in range(13)]
            rule = await service.create_scraping_rule(
                ds.id,
                ScrapingRuleCreate(
                    data_source_id=ds.id,
                    name="Full Rule Config",
                    target_type=TargetType.SHOP_OVERVIEW,
                    config={
                        "timezone": "Asia/Shanghai",
                        "granularity": "DAY",
                        "incremental_mode": "BY_DATE",
                        "backfill_last_n_days": 2,
                        "data_latency": "T+1",
                        "filters": {"shop_id": shop_ids, "region": "east"},
                        "dimensions": ["shop", "category"],
                        "metrics": ["overview", "analysis"],
                        "rate_limit": {"qps": 2, "burst": 2, "concurrency": 1},
                        "top_n": 30,
                        "sort_by": "-total_score",
                        "include_long_tail": True,
                        "session_level": True,
                        "dedupe_key": "{shop_id}:{window_start}:{window_end}",
                        "extra_config": {"cursor": "cursor-1"},
                    },
                ),
            )

            assert rule.config["timezone"] == "Asia/Shanghai"
            assert rule.config["granularity"] == "DAY"
            assert rule.config["incremental_mode"] == "BY_DATE"
            assert rule.config["data_latency"] == "T+1"
            assert len(rule.config["filters"]["shop_id"]) == 13
            assert rule.config["top_n"] == 30
            assert rule.config["sort_by"] == "-total_score"

    async def test_create_rule_for_inactive_source_fails(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            ds = await service.create(
                DataSourceCreate(
                    name="Inactive DS",
                    type=SchemaDataSourceType.DOUYIN_API,
                    config={"api_key": "key", "api_secret": "secret"},
                    status=DataSourceStatus.INACTIVE,
                ),
                user_id=test_user.id,
            )

            rule_data = ScrapingRuleCreate(
                data_source_id=ds.id,
                name="Test Rule",
                target_type=TargetType.ORDER_FULFILLMENT,
            )

            with pytest.raises(BusinessException) as exc_info:
                await service.create_scraping_rule(ds.id, rule_data)
            assert exc_info.value.code == ErrorCode.DATA_VALIDATION_FAILED

    async def test_list_scraping_rules(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            ds = await service.create(
                DataSourceCreate(
                    name="DS for List Rules",
                    type=SchemaDataSourceType.DOUYIN_API,
                    config={"api_key": "key", "api_secret": "secret"},
                ),
                user_id=test_user.id,
            )

            for i in range(3):
                await service.create_scraping_rule(
                    ds.id,
                    ScrapingRuleCreate(
                        data_source_id=ds.id,
                        name=f"Rule {i}",
                        target_type=TargetType.ORDER_FULFILLMENT,
                    ),
                )

            rules = await service.list_scraping_rules(ds.id)
            assert len(rules) == 3

    async def test_update_scraping_rule(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            ds = await service.create(
                DataSourceCreate(
                    name="DS for Update Rule",
                    type=SchemaDataSourceType.DOUYIN_API,
                    config={"api_key": "key", "api_secret": "secret"},
                ),
                user_id=test_user.id,
            )

            rule = await service.create_scraping_rule(
                ds.id,
                ScrapingRuleCreate(
                    data_source_id=ds.id,
                    name="Original Rule Name",
                    target_type=TargetType.ORDER_FULFILLMENT,
                ),
            )

            updated = await service.update_scraping_rule(
                rule.id,
                ScrapingRuleUpdate(name="Updated Rule Name"),
            )

            assert updated.name == "Updated Rule Name"

    async def test_delete_scraping_rule(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            ds = await service.create(
                DataSourceCreate(
                    name="DS for Delete Rule",
                    type=SchemaDataSourceType.DOUYIN_API,
                    config={"api_key": "key", "api_secret": "secret"},
                ),
                user_id=test_user.id,
            )

            rule = await service.create_scraping_rule(
                ds.id,
                ScrapingRuleCreate(
                    data_source_id=ds.id,
                    name="To Delete",
                    target_type=TargetType.ORDER_FULFILLMENT,
                ),
            )

            await service.delete_scraping_rule(rule.id)

            rules = await service.list_scraping_rules(ds.id)
            assert len(rules) == 0


@pytest.mark.asyncio
class TestCollectionTriggerIntegration:
    async def test_trigger_collection(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            ds = await service.create(
                DataSourceCreate(
                    name="DS for Collection",
                    type=SchemaDataSourceType.DOUYIN_API,
                    config={"api_key": "key", "api_secret": "secret"},
                ),
                user_id=test_user.id,
            )

            await service.create_scraping_rule(
                ds.id,
                ScrapingRuleCreate(
                    data_source_id=ds.id,
                    name="Collection Rule",
                    target_type=TargetType.ORDER_FULFILLMENT,
                ),
            )

            result = await service.trigger_collection(ds.id)
            assert result["total"] == 1
            assert result["data_source_id"] == ds.id
            assert len(result["triggered_rules"]) == 1
            assert result["triggered_rules"][0]["task_id"]
            assert result["triggered_rules"][0]["status"] == "queued"

    async def test_trigger_collection_specific_rule(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            ds = await service.create(
                DataSourceCreate(
                    name="DS for Specific Rule",
                    type=SchemaDataSourceType.DOUYIN_API,
                    config={"api_key": "key", "api_secret": "secret"},
                ),
                user_id=test_user.id,
            )

            rule1 = await service.create_scraping_rule(
                ds.id,
                ScrapingRuleCreate(
                    data_source_id=ds.id,
                    name="Rule 1",
                    target_type=TargetType.ORDER_FULFILLMENT,
                ),
            )

            await service.create_scraping_rule(
                ds.id,
                ScrapingRuleCreate(
                    data_source_id=ds.id,
                    name="Rule 2",
                    target_type=TargetType.PRODUCT,
                ),
            )

            result = await service.trigger_collection(ds.id, rule_id=rule1.id)
            assert result["total"] == 1
            assert result["triggered_rules"][0]["rule_id"] == rule1.id
            assert result["triggered_rules"][0]["task_id"]
            assert result["triggered_rules"][0]["status"] == "queued"

    async def test_trigger_collection_inactive_source_fails(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            ds = await service.create(
                DataSourceCreate(
                    name="Inactive DS for Collection",
                    type=SchemaDataSourceType.DOUYIN_API,
                    config={"api_key": "key", "api_secret": "secret"},
                    status=DataSourceStatus.INACTIVE,
                ),
                user_id=test_user.id,
            )

            with pytest.raises(BusinessException) as exc_info:
                await service.trigger_collection(ds.id)
            assert exc_info.value.code == ErrorCode.DATA_VALIDATION_FAILED


@pytest.mark.asyncio
class TestDataSourceServiceValidationIntegration:
    async def test_create_with_invalid_douyin_api_config(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            with pytest.raises(BusinessException) as exc_info:
                await service.create(
                    DataSourceCreate(
                        name="Invalid Config",
                        type=SchemaDataSourceType.DOUYIN_API,
                        config={"api_key": "", "api_secret": ""},
                    ),
                    user_id=test_user.id,
                )
            assert exc_info.value.code == ErrorCode.DATA_VALIDATION_FAILED
            assert "api_key" in exc_info.value.msg or "api_secret" in exc_info.value.msg

    async def test_create_with_file_upload_config(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            rule_repo = ScrapingRuleRepository(session)
            service = DataSourceService(ds_repo, rule_repo, session)

            with pytest.raises(BusinessException) as exc_info:
                await service.create(
                    DataSourceCreate(
                        name="File Upload No Path",
                        type=SchemaDataSourceType.FILE_UPLOAD,
                        config={},
                    ),
                    user_id=test_user.id,
                )
            assert exc_info.value.code == ErrorCode.DATA_VALIDATION_FAILED
