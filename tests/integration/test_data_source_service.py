import pytest

from src.domains.data_source.enums import DataSourceStatus
from src.domains.data_source.repository import DataSourceRepository
from src.domains.data_source.schemas import (
    DataSourceCreate,
    DataSourceUpdate,
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
            service = DataSourceService(ds_repo=ds_repo, session=session)

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
            service = DataSourceService(ds_repo=ds_repo, session=session)

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
            service = DataSourceService(ds_repo=ds_repo, session=session)

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
            service = DataSourceService(ds_repo=ds_repo, session=session)

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
            service = DataSourceService(ds_repo=ds_repo, session=session)

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
            assert len(active_items) == 3

            named_items, total_named = await service.list_paginated(
                page=1, size=10, name="DS 1"
            )
            assert total_named == 1
            assert named_items[0].name == "DS 1"

    async def test_update_data_source(self, test_db, test_user):
        async with test_db() as session:
            ds_repo = DataSourceRepository(session)
            service = DataSourceService(ds_repo=ds_repo, session=session)

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
            service = DataSourceService(ds_repo=ds_repo, session=session)

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
            service = DataSourceService(ds_repo=ds_repo, session=session)

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
            service = DataSourceService(ds_repo=ds_repo, session=session)

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
            service = DataSourceService(ds_repo=ds_repo, session=session)

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
