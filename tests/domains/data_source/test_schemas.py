from datetime import datetime

import pytest
from pydantic import ValidationError

from src.domains.data_source.schemas import (
    DataSourceCreate,
    DataSourceResponse,
    DataSourceStatus,
    DataSourceType,
    DataSourceUpdate,
    ScrapingRuleCreate,
    ScrapingRuleResponse,
    ScrapingRuleType,
    ScrapingRuleUpdate,
)


class TestDataSourceType:
    def test_enum_values(self):
        assert DataSourceType.DOUYIN_API == "douyin_api"
        assert DataSourceType.FILE_UPLOAD == "file_upload"
        assert DataSourceType.DATABASE == "database"
        assert DataSourceType.WEBHOOK == "webhook"


class TestDataSourceStatus:
    def test_enum_values(self):
        assert DataSourceStatus.ACTIVE == "active"
        assert DataSourceStatus.INACTIVE == "inactive"
        assert DataSourceStatus.ERROR == "error"


class TestScrapingRuleType:
    def test_enum_values(self):
        assert ScrapingRuleType.ORDERS == "orders"
        assert ScrapingRuleType.PRODUCTS == "products"
        assert ScrapingRuleType.USERS == "users"
        assert ScrapingRuleType.COMMENTS == "comments"


class TestDataSourceCreate:
    def test_valid_creation(self):
        ds = DataSourceCreate(
            name="Test Data Source",
            type=DataSourceType.DOUYIN_API,
            config={"api_key": "test_key"},
            description="Test description",
        )
        assert ds.name == "Test Data Source"
        assert ds.type == DataSourceType.DOUYIN_API
        assert ds.config == {"api_key": "test_key"}
        assert ds.status == DataSourceStatus.ACTIVE
        assert ds.description == "Test description"

    def test_default_values(self):
        ds = DataSourceCreate(name="Test", type=DataSourceType.DATABASE)
        assert ds.config == {}
        assert ds.status == DataSourceStatus.ACTIVE
        assert ds.description is None

    def test_name_required(self):
        with pytest.raises(ValidationError) as exc_info:
            DataSourceCreate(type=DataSourceType.DOUYIN_API)
        assert "name" in str(exc_info.value)

    def test_type_required(self):
        with pytest.raises(ValidationError) as exc_info:
            DataSourceCreate(name="Test")
        assert "type" in str(exc_info.value)

    def test_name_min_length(self):
        with pytest.raises(ValidationError) as exc_info:
            DataSourceCreate(name="", type=DataSourceType.DOUYIN_API)
        assert "name" in str(exc_info.value)

    def test_name_max_length(self):
        with pytest.raises(ValidationError) as exc_info:
            DataSourceCreate(name="x" * 101, type=DataSourceType.DOUYIN_API)
        assert "name" in str(exc_info.value)

    def test_description_max_length(self):
        with pytest.raises(ValidationError) as exc_info:
            DataSourceCreate(
                name="Test",
                type=DataSourceType.DOUYIN_API,
                description="x" * 501,
            )
        assert "description" in str(exc_info.value)

    def test_invalid_type(self):
        with pytest.raises(ValidationError) as exc_info:
            DataSourceCreate(name="Test", type="invalid_type")
        assert "type" in str(exc_info.value)


class TestDataSourceUpdate:
    def test_valid_update(self):
        ds = DataSourceUpdate(name="Updated Name")
        assert ds.name == "Updated Name"
        assert ds.config is None
        assert ds.status is None
        assert ds.description is None

    def test_partial_update(self):
        ds = DataSourceUpdate(status=DataSourceStatus.INACTIVE)
        assert ds.name is None
        assert ds.status == DataSourceStatus.INACTIVE

    def test_empty_update(self):
        ds = DataSourceUpdate()
        assert ds.name is None
        assert ds.config is None
        assert ds.status is None
        assert ds.description is None

    def test_name_min_length_validation(self):
        with pytest.raises(ValidationError) as exc_info:
            DataSourceUpdate(name="")
        assert "name" in str(exc_info.value)

    def test_name_max_length_validation(self):
        with pytest.raises(ValidationError) as exc_info:
            DataSourceUpdate(name="x" * 101)
        assert "name" in str(exc_info.value)

    def test_description_max_length_validation(self):
        with pytest.raises(ValidationError) as exc_info:
            DataSourceUpdate(description="x" * 501)
        assert "description" in str(exc_info.value)


class TestDataSourceResponse:
    def test_valid_response(self):
        now = datetime.now()
        ds = DataSourceResponse(
            id=1,
            name="Test Data Source",
            type=DataSourceType.DOUYIN_API,
            config={"api_key": "test"},
            status=DataSourceStatus.ACTIVE,
            description="Test description",
            created_at=now,
            updated_at=now,
        )
        assert ds.id == 1
        assert ds.name == "Test Data Source"
        assert ds.created_at == now
        assert ds.updated_at == now

    def test_from_attributes_config(self):
        assert DataSourceResponse.model_config.get("from_attributes") is True


class TestScrapingRuleCreate:
    def test_valid_creation(self):
        rule = ScrapingRuleCreate(
            data_source_id=1,
            name="Test Rule",
            rule_type=ScrapingRuleType.ORDERS,
            config={"param": "value"},
            schedule="0 */6 * * *",
            is_active=True,
            description="Test rule description",
        )
        assert rule.data_source_id == 1
        assert rule.name == "Test Rule"
        assert rule.rule_type == ScrapingRuleType.ORDERS
        assert rule.config == {"param": "value"}
        assert rule.schedule == "0 */6 * * *"
        assert rule.is_active is True
        assert rule.description == "Test rule description"

    def test_default_values(self):
        rule = ScrapingRuleCreate(
            data_source_id=1,
            name="Test Rule",
            rule_type=ScrapingRuleType.PRODUCTS,
        )
        assert rule.config == {}
        assert rule.schedule is None
        assert rule.is_active is True
        assert rule.description is None

    def test_data_source_id_required(self):
        with pytest.raises(ValidationError) as exc_info:
            ScrapingRuleCreate(name="Test", rule_type=ScrapingRuleType.ORDERS)
        assert "data_source_id" in str(exc_info.value)

    def test_name_required(self):
        with pytest.raises(ValidationError) as exc_info:
            ScrapingRuleCreate(data_source_id=1, rule_type=ScrapingRuleType.ORDERS)
        assert "name" in str(exc_info.value)

    def test_rule_type_required(self):
        with pytest.raises(ValidationError) as exc_info:
            ScrapingRuleCreate(data_source_id=1, name="Test")
        assert "rule_type" in str(exc_info.value)

    def test_name_min_length(self):
        with pytest.raises(ValidationError) as exc_info:
            ScrapingRuleCreate(
                data_source_id=1, name="", rule_type=ScrapingRuleType.ORDERS
            )
        assert "name" in str(exc_info.value)

    def test_name_max_length(self):
        with pytest.raises(ValidationError) as exc_info:
            ScrapingRuleCreate(
                data_source_id=1, name="x" * 101, rule_type=ScrapingRuleType.ORDERS
            )
        assert "name" in str(exc_info.value)

    def test_schedule_max_length(self):
        with pytest.raises(ValidationError) as exc_info:
            ScrapingRuleCreate(
                data_source_id=1,
                name="Test",
                rule_type=ScrapingRuleType.ORDERS,
                schedule="x" * 101,
            )
        assert "schedule" in str(exc_info.value)

    def test_description_max_length(self):
        with pytest.raises(ValidationError) as exc_info:
            ScrapingRuleCreate(
                data_source_id=1,
                name="Test",
                rule_type=ScrapingRuleType.ORDERS,
                description="x" * 501,
            )
        assert "description" in str(exc_info.value)


class TestScrapingRuleUpdate:
    def test_valid_update(self):
        rule = ScrapingRuleUpdate(name="Updated Rule")
        assert rule.name == "Updated Rule"
        assert rule.config is None
        assert rule.schedule is None
        assert rule.is_active is None
        assert rule.description is None

    def test_partial_update(self):
        rule = ScrapingRuleUpdate(is_active=False)
        assert rule.name is None
        assert rule.is_active is False

    def test_empty_update(self):
        rule = ScrapingRuleUpdate()
        assert rule.name is None
        assert rule.config is None
        assert rule.schedule is None
        assert rule.is_active is None
        assert rule.description is None

    def test_name_min_length_validation(self):
        with pytest.raises(ValidationError) as exc_info:
            ScrapingRuleUpdate(name="")
        assert "name" in str(exc_info.value)

    def test_name_max_length_validation(self):
        with pytest.raises(ValidationError) as exc_info:
            ScrapingRuleUpdate(name="x" * 101)
        assert "name" in str(exc_info.value)

    def test_schedule_max_length_validation(self):
        with pytest.raises(ValidationError) as exc_info:
            ScrapingRuleUpdate(schedule="x" * 101)
        assert "schedule" in str(exc_info.value)

    def test_description_max_length_validation(self):
        with pytest.raises(ValidationError) as exc_info:
            ScrapingRuleUpdate(description="x" * 501)
        assert "description" in str(exc_info.value)


class TestScrapingRuleResponse:
    def test_valid_response(self):
        now = datetime.now()
        rule = ScrapingRuleResponse(
            id=1,
            data_source_id=2,
            name="Test Rule",
            rule_type=ScrapingRuleType.COMMENTS,
            config={"param": "value"},
            schedule="0 0 * * *",
            is_active=True,
            description="Test description",
            created_at=now,
            updated_at=now,
        )
        assert rule.id == 1
        assert rule.data_source_id == 2
        assert rule.name == "Test Rule"
        assert rule.rule_type == ScrapingRuleType.COMMENTS
        assert rule.created_at == now
        assert rule.updated_at == now

    def test_from_attributes_config(self):
        assert ScrapingRuleResponse.model_config.get("from_attributes") is True


class TestSchemaSerialization:
    def test_datasource_create_serialization(self):
        ds = DataSourceCreate(
            name="Test",
            type=DataSourceType.DATABASE,
            config={"host": "localhost", "port": 5432},
        )
        json_str = ds.model_dump_json()
        assert "Test" in json_str
        assert "database" in json_str
        assert "localhost" in json_str

    def test_scraping_rule_response_serialization(self):
        now = datetime.now()
        rule = ScrapingRuleResponse(
            id=1,
            data_source_id=2,
            name="Test Rule",
            rule_type=ScrapingRuleType.ORDERS,
            config={},
            schedule=None,
            is_active=True,
            description=None,
            created_at=now,
            updated_at=now,
        )
        data = rule.model_dump()
        assert data["id"] == 1
        assert data["name"] == "Test Rule"
        assert data["rule_type"] == "orders"
