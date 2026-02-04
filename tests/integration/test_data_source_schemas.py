"""Integration tests for data source schemas with API endpoints."""

import pytest

from src.domains.data_source.schemas import (
    DataSourceCreate,
    DataSourceStatus,
    DataSourceType,
    DataSourceUpdate,
    ScrapingRuleCreate,
    ScrapingRuleType,
    ScrapingRuleUpdate,
)

pytestmark = pytest.mark.skip(reason="API endpoints not yet implemented")


class TestDataSourceCreateSchema:
    async def test_create_endpoint_accepts_valid_schema(self, test_client):
        payload = DataSourceCreate(
            name="Test Douyin Shop",
            type=DataSourceType.DOUYIN_API,
            config={"api_key": "test_key", "api_secret": "test_secret"},
            description="Test data source for integration",
        )
        response = await test_client.post(
            "/api/v1/data-sources",
            json=payload.model_dump(),
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Test Douyin Shop"
        assert data["type"] == "douyin_api"

    async def test_create_endpoint_rejects_invalid_type(self, test_client):
        response = await test_client.post(
            "/api/v1/data-sources",
            json={"name": "Test", "type": "invalid_type"},
        )
        assert response.status_code == 422

    async def test_create_endpoint_rejects_empty_name(self, test_client):
        payload = DataSourceCreate(
            name="",
            type=DataSourceType.DOUYIN_API,
        )
        response = await test_client.post(
            "/api/v1/data-sources",
            json=payload.model_dump(),
        )
        assert response.status_code == 422

    async def test_create_endpoint_rejects_long_description(self, test_client):
        payload = DataSourceCreate(
            name="Test",
            type=DataSourceType.DOUYIN_API,
            description="x" * 501,
        )
        response = await test_client.post(
            "/api/v1/data-sources",
            json=payload.model_dump(),
        )
        assert response.status_code == 422


class TestDataSourceUpdateSchema:
    async def test_update_endpoint_accepts_partial_update(self, test_client):
        create_payload = DataSourceCreate(
            name="Original Name",
            type=DataSourceType.DATABASE,
        )
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json=create_payload.model_dump(),
        )
        ds_id = create_response.json()["data"]["id"]

        update_payload = DataSourceUpdate(name="Updated Name")
        response = await test_client.put(
            f"/api/v1/data-sources/{ds_id}",
            json=update_payload.model_dump(exclude_none=True),
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Name"

    async def test_update_endpoint_accepts_status_change(self, test_client):
        create_payload = DataSourceCreate(
            name="Test DS",
            type=DataSourceType.WEBHOOK,
            status=DataSourceStatus.ACTIVE,
        )
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json=create_payload.model_dump(),
        )
        ds_id = create_response.json()["data"]["id"]

        update_payload = DataSourceUpdate(status=DataSourceStatus.INACTIVE)
        response = await test_client.put(
            f"/api/v1/data-sources/{ds_id}",
            json=update_payload.model_dump(exclude_none=True),
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "inactive"

    async def test_update_endpoint_accepts_config_update(self, test_client):
        create_payload = DataSourceCreate(
            name="Test DS",
            type=DataSourceType.DATABASE,
            config={"host": "old_host"},
        )
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json=create_payload.model_dump(),
        )
        ds_id = create_response.json()["data"]["id"]

        update_payload = DataSourceUpdate(config={"host": "new_host", "port": 5432})
        response = await test_client.put(
            f"/api/v1/data-sources/{ds_id}",
            json=update_payload.model_dump(exclude_none=True),
        )
        assert response.status_code == 200
        assert response.json()["data"]["config"]["host"] == "new_host"


class TestScrapingRuleCreateSchema:
    async def test_create_scraping_rule_endpoint(self, test_client):
        ds_payload = DataSourceCreate(name="Test DS", type=DataSourceType.DOUYIN_API)
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json=ds_payload.model_dump(),
        )
        ds_id = ds_response.json()["data"]["id"]

        rule_payload = ScrapingRuleCreate(
            data_source_id=ds_id,
            name="Order Collection Rule",
            rule_type=ScrapingRuleType.ORDERS,
            config={"batch_size": 100},
            schedule="0 */6 * * *",
            description="Collect orders every 6 hours",
        )
        response = await test_client.post(
            "/api/v1/scraping-rules",
            json=rule_payload.model_dump(),
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Order Collection Rule"
        assert data["rule_type"] == "orders"
        assert data["data_source_id"] == ds_id

    async def test_create_scraping_rule_rejects_missing_data_source(self, test_client):
        rule_payload = ScrapingRuleCreate(
            data_source_id=99999,
            name="Test Rule",
            rule_type=ScrapingRuleType.PRODUCTS,
        )
        response = await test_client.post(
            "/api/v1/scraping-rules",
            json=rule_payload.model_dump(),
        )
        assert response.status_code == 404


class TestScrapingRuleUpdateSchema:
    async def test_update_scraping_rule_schedule(self, test_client):
        ds_payload = DataSourceCreate(name="Test DS", type=DataSourceType.DOUYIN_API)
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json=ds_payload.model_dump(),
        )
        ds_id = ds_response.json()["data"]["id"]

        rule_payload = ScrapingRuleCreate(
            data_source_id=ds_id,
            name="Test Rule",
            rule_type=ScrapingRuleType.ORDERS,
            schedule="0 0 * * *",
        )
        rule_response = await test_client.post(
            "/api/v1/scraping-rules",
            json=rule_payload.model_dump(),
        )
        rule_id = rule_response.json()["data"]["id"]

        update_payload = ScrapingRuleUpdate(schedule="0 */12 * * *")
        response = await test_client.put(
            f"/api/v1/scraping-rules/{rule_id}",
            json=update_payload.model_dump(exclude_none=True),
        )
        assert response.status_code == 200
        assert response.json()["data"]["schedule"] == "0 */12 * * *"

    async def test_update_scraping_rule_deactivation(self, test_client):
        ds_payload = DataSourceCreate(name="Test DS", type=DataSourceType.DOUYIN_API)
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json=ds_payload.model_dump(),
        )
        ds_id = ds_response.json()["data"]["id"]

        rule_payload = ScrapingRuleCreate(
            data_source_id=ds_id,
            name="Test Rule",
            rule_type=ScrapingRuleType.PRODUCTS,
            is_active=True,
        )
        rule_response = await test_client.post(
            "/api/v1/scraping-rules",
            json=rule_payload.model_dump(),
        )
        rule_id = rule_response.json()["data"]["id"]

        update_payload = ScrapingRuleUpdate(is_active=False)
        response = await test_client.put(
            f"/api/v1/scraping-rules/{rule_id}",
            json=update_payload.model_dump(exclude_none=True),
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_active"] is False


class TestSchemaResponseStructure:
    async def test_datasource_response_contains_all_fields(self, test_client):
        payload = DataSourceCreate(
            name="Full Field Test",
            type=DataSourceType.FILE_UPLOAD,
            config={"path": "/uploads"},
            status=DataSourceStatus.ACTIVE,
            description="Testing all response fields",
        )
        response = await test_client.post(
            "/api/v1/data-sources",
            json=payload.model_dump(),
        )
        assert response.status_code == 200
        data = response.json()["data"]

        required_fields = {
            "id",
            "name",
            "type",
            "config",
            "status",
            "description",
            "created_at",
            "updated_at",
        }
        assert required_fields.issubset(set(data.keys()))

    async def test_scraping_rule_response_contains_all_fields(self, test_client):
        ds_payload = DataSourceCreate(name="Test DS", type=DataSourceType.DATABASE)
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json=ds_payload.model_dump(),
        )
        ds_id = ds_response.json()["data"]["id"]

        rule_payload = ScrapingRuleCreate(
            data_source_id=ds_id,
            name="Field Test Rule",
            rule_type=ScrapingRuleType.USERS,
            config={"limit": 1000},
            schedule="0 0 * * 0",
            is_active=True,
            description="Testing all response fields",
        )
        response = await test_client.post(
            "/api/v1/scraping-rules",
            json=rule_payload.model_dump(),
        )
        assert response.status_code == 200
        data = response.json()["data"]

        required_fields = {
            "id",
            "data_source_id",
            "name",
            "rule_type",
            "config",
            "schedule",
            "is_active",
            "description",
            "created_at",
            "updated_at",
        }
        assert required_fields.issubset(set(data.keys()))
