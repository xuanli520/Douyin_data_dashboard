import pytest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.exc import IntegrityError as SAIntegrityError

from src.domains.data_source.enums import DataSourceStatus, DataSourceType
from src.domains.data_source.models import DataSource
from src.domains.data_source.repository import (
    DataSourceRepository,
    ScrapingRuleRepository,
)
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


class TestDataSourceRepositoryUnit:
    @pytest.mark.asyncio
    async def test_build_conditions_empty(self):
        session = AsyncMock()
        repo = DataSourceRepository(session)
        conds = repo._build_conditions()
        assert conds == []

    @pytest.mark.asyncio
    async def test_build_conditions_with_status(self):
        session = AsyncMock()
        repo = DataSourceRepository(session)
        conds = repo._build_conditions(status=DataSourceStatus.ACTIVE)
        assert len(conds) == 1

    @pytest.mark.asyncio
    async def test_build_conditions_with_type(self):
        session = AsyncMock()
        repo = DataSourceRepository(session)
        conds = repo._build_conditions(source_type=DataSourceType.DOUYIN_SHOP)
        assert len(conds) == 1

    @pytest.mark.asyncio
    async def test_build_conditions_with_name(self):
        session = AsyncMock()
        repo = DataSourceRepository(session)
        conds = repo._build_conditions(name="test")
        assert len(conds) == 1

    @pytest.mark.asyncio
    async def test_build_conditions_multiple(self):
        session = AsyncMock()
        repo = DataSourceRepository(session)
        conds = repo._build_conditions(
            status=DataSourceStatus.ACTIVE,
            source_type=DataSourceType.DOUYIN_SHOP,
            name="test",
        )
        assert len(conds) == 3


class TestDataSourceRepositoryIntegration:
    async def test_create_data_source(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            data = {
                "name": "Test DataSource",
                "description": "Test description",
                "source_type": DataSourceType.DOUYIN_SHOP,
                "status": DataSourceStatus.ACTIVE,
                "shop_id": "123456",
            }
            ds = await repo.create(data)

            assert ds.id is not None
            assert ds.name == "Test DataSource"
            assert ds.source_type == DataSourceType.DOUYIN_SHOP

    async def test_create_integrity_error_raises_business_exception(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)

            # Mock execute to simulate unique constraint violation
            original_add = session.add

            def mock_add_with_error(instance):
                if (
                    isinstance(instance, DataSource)
                    and instance.name == "Conflict Name"
                ):
                    error = SAIntegrityError(
                        "statement",
                        "params",
                        Exception("unique constraint failed: name"),
                    )
                    error.orig = MagicMock()
                    error.orig.constraint_name = "ix_data_sources_name"
                    error.orig.sqlstate = "23505"
                    raise error
                original_add(instance)

            session.add = mock_add_with_error

            with pytest.raises(BusinessException) as exc_info:
                await repo.create(
                    {
                        "name": "Conflict Name",
                        "source_type": DataSourceType.DOUYIN_SHOP,
                    }
                )
            assert exc_info.value.code == ErrorCode.DATASOURCE_NAME_CONFLICT

    async def test_get_by_id(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            data = {"name": "Test DS", "source_type": DataSourceType.DOUYIN_SHOP}
            created = await repo.create(data)

            found = await repo.get_by_id(created.id)
            assert found is not None
            assert found.id == created.id
            assert found.name == "Test DS"

    async def test_get_by_id_not_found(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            found = await repo.get_by_id(9999)
            assert found is None

    async def test_get_by_id_with_rules(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            ds_data = {
                "name": "Test DS with Rules",
                "source_type": DataSourceType.DOUYIN_SHOP,
            }
            ds = await repo.create(ds_data)

            rule_repo = ScrapingRuleRepository(session)
            await rule_repo.create(
                {
                    "name": "Test Rule",
                    "data_source_id": ds.id,
                }
            )

            found = await repo.get_by_id(ds.id, include_rules=True)
            assert found is not None
            assert len(found.scraping_rules) == 1

    async def test_update_data_source(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            data = {"name": "Original Name", "source_type": DataSourceType.DOUYIN_SHOP}
            created = await repo.create(data)

            updated = await repo.update(created.id, {"name": "Updated Name"})
            assert updated.name == "Updated Name"

    async def test_update_not_found_raises_error(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            with pytest.raises(BusinessException) as exc_info:
                await repo.update(9999, {"name": "New Name"})
            assert exc_info.value.code == ErrorCode.DATASOURCE_NOT_FOUND

    async def test_update_with_none_value_skips_field(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            data = {
                "name": "Original Name",
                "description": "Original Desc",
                "source_type": DataSourceType.DOUYIN_SHOP,
            }
            created = await repo.create(data)

            updated = await repo.update(
                created.id, {"name": "New Name", "description": None}
            )
            assert updated.name == "New Name"
            assert updated.description == "Original Desc"

    async def test_delete_data_source(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            data = {"name": "To Delete", "source_type": DataSourceType.DOUYIN_SHOP}
            created = await repo.create(data)

            await repo.delete(created.id)

            found = await repo.get_by_id(created.id)
            assert found is None

    async def test_delete_not_found_raises_error(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            with pytest.raises(BusinessException) as exc_info:
                await repo.delete(9999)
            assert exc_info.value.code == ErrorCode.DATASOURCE_NOT_FOUND

    async def test_get_paginated(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            for i in range(5):
                await repo.create(
                    {
                        "name": f"DS {i}",
                        "source_type": DataSourceType.DOUYIN_SHOP,
                    }
                )

            items, total = await repo.get_paginated(page=1, size=3)
            assert len(items) == 3
            assert total == 5

    async def test_get_paginated_with_filters(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            await repo.create(
                {
                    "name": "Active DS",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                    "status": DataSourceStatus.ACTIVE,
                }
            )
            await repo.create(
                {
                    "name": "Inactive DS",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                    "status": DataSourceStatus.INACTIVE,
                }
            )

            items, total = await repo.get_paginated(
                page=1, size=10, status=DataSourceStatus.ACTIVE
            )
            assert len(items) == 1
            assert items[0].name == "Active DS"

    async def test_get_paginated_with_name_filter(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            await repo.create(
                {
                    "name": "Special Name",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                }
            )
            await repo.create(
                {
                    "name": "Other",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                }
            )

            items, total = await repo.get_paginated(page=1, size=10, name="Special")
            assert len(items) == 1
            assert items[0].name == "Special Name"

    async def test_get_by_status(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            await repo.create(
                {
                    "name": "Active 1",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                    "status": DataSourceStatus.ACTIVE,
                }
            )
            await repo.create(
                {
                    "name": "Active 2",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                    "status": DataSourceStatus.ACTIVE,
                }
            )
            await repo.create(
                {
                    "name": "Inactive",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                    "status": DataSourceStatus.INACTIVE,
                }
            )

            active_items = await repo.get_by_status(DataSourceStatus.ACTIVE)
            assert len(active_items) == 2

    async def test_get_by_type(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            await repo.create(
                {
                    "name": "Douyin Shop",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                }
            )
            await repo.create(
                {
                    "name": "Douyin App",
                    "source_type": DataSourceType.DOUYIN_APP,
                }
            )

            shop_items = await repo.get_by_type(DataSourceType.DOUYIN_SHOP)
            assert len(shop_items) == 1
            assert shop_items[0].name == "Douyin Shop"

    async def test_get_by_shop_id(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            await repo.create(
                {
                    "name": "Shop DS",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                    "shop_id": "SHOP123",
                }
            )

            found = await repo.get_by_shop_id("SHOP123")
            assert found is not None
            assert found.name == "Shop DS"

    async def test_get_by_shop_id_not_found(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            found = await repo.get_by_shop_id("NONEXISTENT")
            assert found is None

    async def test_update_status(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            data = {
                "name": "Status Test",
                "source_type": DataSourceType.DOUYIN_SHOP,
                "status": DataSourceStatus.ACTIVE,
            }
            created = await repo.create(data)

            updated = await repo.update_status(created.id, DataSourceStatus.INACTIVE)
            assert updated.status == DataSourceStatus.INACTIVE

    async def test_update_last_used(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            data = {"name": "Last Used Test", "source_type": DataSourceType.DOUYIN_SHOP}
            created = await repo.create(data)
            assert created.last_used_at is None

            await repo.update_last_used(created.id)

            found = await repo.get_by_id(created.id)
            assert found.last_used_at is not None

    async def test_record_error(self, test_db):
        async with test_db() as session:
            repo = DataSourceRepository(session)
            data = {
                "name": "Error Test",
                "source_type": DataSourceType.DOUYIN_SHOP,
                "status": DataSourceStatus.ACTIVE,
            }
            created = await repo.create(data)

            await repo.record_error(created.id, "Connection timeout")

            found = await repo.get_by_id(created.id)
            assert found.last_error_at is not None
            assert found.last_error_msg == "Connection timeout"
            assert found.status == DataSourceStatus.ERROR


class TestScrapingRuleRepositoryIntegration:
    async def test_create_scraping_rule(self, test_db):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            ds = await ds_repo.create(
                {
                    "name": "Test DS",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                }
            )

            rule_repo = ScrapingRuleRepository(session)
            rule = await rule_repo.create(
                {
                    "name": "Test Rule",
                    "data_source_id": ds.id,
                }
            )

            assert rule.id is not None
            assert rule.name == "Test Rule"
            assert rule.data_source_id == ds.id

    async def test_get_by_id(self, test_db):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            ds = await ds_repo.create(
                {
                    "name": "Test DS",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                }
            )

            rule_repo = ScrapingRuleRepository(session)
            created = await rule_repo.create(
                {
                    "name": "Test Rule",
                    "data_source_id": ds.id,
                }
            )

            found = await rule_repo.get_by_id(created.id)
            assert found is not None
            assert found.id == created.id

    async def test_get_by_id_not_found(self, test_db):
        async with test_db() as session:
            rule_repo = ScrapingRuleRepository(session)
            found = await rule_repo.get_by_id(9999)
            assert found is None

    async def test_get_by_data_source(self, test_db):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            ds1 = await ds_repo.create(
                {
                    "name": "DS 1",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                }
            )
            ds2 = await ds_repo.create(
                {
                    "name": "DS 2",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                }
            )

            rule_repo = ScrapingRuleRepository(session)
            await rule_repo.create(
                {
                    "name": "Rule 1 for DS1",
                    "data_source_id": ds1.id,
                }
            )
            await rule_repo.create(
                {
                    "name": "Rule 2 for DS1",
                    "data_source_id": ds1.id,
                }
            )
            await rule_repo.create(
                {
                    "name": "Rule for DS2",
                    "data_source_id": ds2.id,
                }
            )

            ds1_rules = await rule_repo.get_by_data_source(ds1.id)
            assert len(ds1_rules) == 2

    async def test_update_scraping_rule(self, test_db):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            ds = await ds_repo.create(
                {
                    "name": "Test DS",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                }
            )

            rule_repo = ScrapingRuleRepository(session)
            created = await rule_repo.create(
                {
                    "name": "Original Rule Name",
                    "data_source_id": ds.id,
                }
            )

            updated = await rule_repo.update(created.id, {"name": "Updated Rule Name"})
            assert updated.name == "Updated Rule Name"

    async def test_update_not_found_raises_error(self, test_db):
        async with test_db() as session:
            rule_repo = ScrapingRuleRepository(session)
            with pytest.raises(BusinessException) as exc_info:
                await rule_repo.update(9999, {"name": "New Name"})
            assert exc_info.value.code == ErrorCode.SCRAPING_RULE_NOT_FOUND

    async def test_delete_scraping_rule(self, test_db):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            ds = await ds_repo.create(
                {
                    "name": "Test DS",
                    "source_type": DataSourceType.DOUYIN_SHOP,
                }
            )

            rule_repo = ScrapingRuleRepository(session)
            created = await rule_repo.create(
                {
                    "name": "To Delete",
                    "data_source_id": ds.id,
                }
            )

            await rule_repo.delete(created.id)

            found = await rule_repo.get_by_id(created.id)
            assert found is None

    async def test_delete_not_found_raises_error(self, test_db):
        async with test_db() as session:
            rule_repo = ScrapingRuleRepository(session)
            with pytest.raises(BusinessException) as exc_info:
                await rule_repo.delete(9999)
            assert exc_info.value.code == ErrorCode.SCRAPING_RULE_NOT_FOUND
