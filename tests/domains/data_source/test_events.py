from datetime import datetime, timezone

import pytest

from src.domains.data_source.enums import DataSourceStatus, DataSourceType
from src.domains.data_source.events import (
    DataSourceCreatedEvent,
    DataSourceStatusChangedEvent,
    DomainEvent,
    ScrapingRuleUpdatedEvent,
)


class TestDomainEvent:
    def test_occurred_at_has_default_value(self):
        event = DomainEvent()
        assert event.occurred_at is not None
        assert isinstance(event.occurred_at, datetime)

    def test_occurred_at_can_be_customized(self):
        custom_time = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        event = DomainEvent(occurred_at=custom_time)
        assert event.occurred_at == custom_time


class TestDataSourceCreatedEvent:
    def test_create_with_required_fields(self):
        event = DataSourceCreatedEvent(
            data_source_id=1,
            name="Test Data Source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )

        assert event.data_source_id == 1
        assert event.name == "Test Data Source"
        assert event.source_type == DataSourceType.DOUYIN_SHOP
        assert event.status == DataSourceStatus.ACTIVE
        assert event.created_by_id is None
        assert event.occurred_at is not None

    def test_create_with_all_fields(self):
        event = DataSourceCreatedEvent(
            data_source_id=2,
            name="Another Data Source",
            source_type=DataSourceType.FILE_IMPORT,
            status=DataSourceStatus.INACTIVE,
            created_by_id=42,
        )

        assert event.data_source_id == 2
        assert event.name == "Another Data Source"
        assert event.source_type == DataSourceType.FILE_IMPORT
        assert event.status == DataSourceStatus.INACTIVE
        assert event.created_by_id == 42

    def test_event_is_frozen(self):
        event = DataSourceCreatedEvent(
            data_source_id=1,
            name="Test",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )

        with pytest.raises(AttributeError):
            event.name = "Modified"

    def test_source_type_is_enum(self):
        for source_type in DataSourceType:
            event = DataSourceCreatedEvent(
                data_source_id=1,
                name="Test",
                source_type=source_type,
                status=DataSourceStatus.ACTIVE,
            )
            assert event.source_type == source_type
            assert isinstance(event.source_type, DataSourceType)

    def test_status_is_enum(self):
        for status in DataSourceStatus:
            event = DataSourceCreatedEvent(
                data_source_id=1,
                name="Test",
                source_type=DataSourceType.DOUYIN_SHOP,
                status=status,
            )
            assert event.status == status
            assert isinstance(event.status, DataSourceStatus)


class TestDataSourceStatusChangedEvent:
    def test_create_with_required_fields(self):
        event = DataSourceStatusChangedEvent(
            data_source_id=1,
            name="Test Data Source",
            old_status=DataSourceStatus.INACTIVE,
            new_status=DataSourceStatus.ACTIVE,
        )

        assert event.data_source_id == 1
        assert event.name == "Test Data Source"
        assert event.old_status == DataSourceStatus.INACTIVE
        assert event.new_status == DataSourceStatus.ACTIVE
        assert event.changed_by_id is None
        assert event.occurred_at is not None

    def test_create_with_all_fields(self):
        event = DataSourceStatusChangedEvent(
            data_source_id=3,
            name="Shop API",
            old_status=DataSourceStatus.ACTIVE,
            new_status=DataSourceStatus.ERROR,
            changed_by_id=99,
        )

        assert event.data_source_id == 3
        assert event.name == "Shop API"
        assert event.old_status == DataSourceStatus.ACTIVE
        assert event.new_status == DataSourceStatus.ERROR
        assert event.changed_by_id == 99

    def test_event_is_frozen(self):
        event = DataSourceStatusChangedEvent(
            data_source_id=1,
            name="Test",
            old_status=DataSourceStatus.ACTIVE,
            new_status=DataSourceStatus.INACTIVE,
        )

        with pytest.raises(AttributeError):
            event.old_status = DataSourceStatus.ERROR

    def test_status_fields_are_enums(self):
        statuses = list(DataSourceStatus)
        for i in range(len(statuses)):
            for j in range(len(statuses)):
                if i != j:
                    event = DataSourceStatusChangedEvent(
                        data_source_id=1,
                        name="Test",
                        old_status=statuses[i],
                        new_status=statuses[j],
                    )
                    assert isinstance(event.old_status, DataSourceStatus)
                    assert isinstance(event.new_status, DataSourceStatus)


class TestScrapingRuleUpdatedEvent:
    def test_create_with_required_fields(self):
        event = ScrapingRuleUpdatedEvent(
            rule_id=1,
            data_source_id=2,
            name="Test Rule",
        )

        assert event.rule_id == 1
        assert event.data_source_id == 2
        assert event.name == "Test Rule"
        assert event.old_config == {}
        assert event.new_config == {}
        assert event.updated_fields == []
        assert event.occurred_at is not None

    def test_create_with_config_changes(self):
        old_config = {"schedule": "0 2 * * *", "target": "orders"}
        new_config = {"schedule": "0 3 * * *", "target": "orders"}

        event = ScrapingRuleUpdatedEvent(
            rule_id=5,
            data_source_id=10,
            name="Updated Rule",
            old_config=old_config,
            new_config=new_config,
            updated_fields=["schedule"],
        )

        assert event.rule_id == 5
        assert event.data_source_id == 10
        assert event.name == "Updated Rule"
        assert event.old_config == old_config
        assert event.new_config == new_config
        assert event.updated_fields == ["schedule"]

    def test_event_is_frozen(self):
        event = ScrapingRuleUpdatedEvent(
            rule_id=1,
            data_source_id=2,
            name="Test",
        )

        with pytest.raises(AttributeError):
            event.name = "Modified"

    def test_config_fields_are_dicts(self):
        event = ScrapingRuleUpdatedEvent(
            rule_id=1,
            data_source_id=2,
            name="Test",
            old_config={"key1": "value1"},
            new_config={"key1": "value2", "key2": "value3"},
        )

        assert isinstance(event.old_config, dict)
        assert isinstance(event.new_config, dict)
        assert event.old_config["key1"] == "value1"
        assert event.new_config["key1"] == "value2"
        assert event.new_config["key2"] == "value3"

    def test_updated_fields_is_list(self):
        event = ScrapingRuleUpdatedEvent(
            rule_id=1,
            data_source_id=2,
            name="Test",
            updated_fields=["field1", "field2", "field3"],
        )

        assert isinstance(event.updated_fields, list)
        assert len(event.updated_fields) == 3
        assert "field1" in event.updated_fields

    def test_empty_updated_fields(self):
        event = ScrapingRuleUpdatedEvent(
            rule_id=1,
            data_source_id=2,
            name="Test",
            updated_fields=[],
        )

        assert event.updated_fields == []


class TestEventInheritance:
    def test_all_events_inherit_from_domain_event(self):
        created_event = DataSourceCreatedEvent(
            data_source_id=1,
            name="Test",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        status_event = DataSourceStatusChangedEvent(
            data_source_id=1,
            name="Test",
            old_status=DataSourceStatus.ACTIVE,
            new_status=DataSourceStatus.INACTIVE,
        )
        rule_event = ScrapingRuleUpdatedEvent(
            rule_id=1,
            data_source_id=2,
            name="Test",
        )

        assert isinstance(created_event, DomainEvent)
        assert isinstance(status_event, DomainEvent)
        assert isinstance(rule_event, DomainEvent)

    def test_all_events_have_occurred_at(self):
        events = [
            DataSourceCreatedEvent(
                data_source_id=1,
                name="Test",
                source_type=DataSourceType.DOUYIN_SHOP,
                status=DataSourceStatus.ACTIVE,
            ),
            DataSourceStatusChangedEvent(
                data_source_id=1,
                name="Test",
                old_status=DataSourceStatus.ACTIVE,
                new_status=DataSourceStatus.INACTIVE,
            ),
            ScrapingRuleUpdatedEvent(
                rule_id=1,
                data_source_id=2,
                name="Test",
            ),
        ]

        for event in events:
            assert hasattr(event, "occurred_at")
            assert isinstance(event.occurred_at, datetime)


class TestEventEquality:
    def test_events_with_same_values_are_not_equal(self):
        event1 = DataSourceCreatedEvent(
            data_source_id=1,
            name="Test",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        event2 = DataSourceCreatedEvent(
            data_source_id=1,
            name="Test",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )

        assert event1 != event2


class TestEventSlots:
    def test_events_have_slots_attribute(self):
        event = DataSourceCreatedEvent(
            data_source_id=1,
            name="Test",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )

        assert hasattr(event, "__slots__")
