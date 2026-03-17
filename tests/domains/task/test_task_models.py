from src.domains.task.enums import (
    TaskDefinitionStatus,
    TaskExecutionStatus,
)
from src.domains.task.models import TaskDefinition, TaskExecution


def test_task_definition_required_fields():
    expected_fields = {
        "id",
        "name",
        "task_type",
        "status",
        "config",
        "created_by_id",
        "updated_by_id",
    }
    assert expected_fields.issubset(set(TaskDefinition.model_fields.keys()))


def test_task_execution_required_fields():
    expected_fields = {
        "id",
        "task_id",
        "queue_task_id",
        "status",
        "trigger_mode",
        "payload",
        "started_at",
        "completed_at",
        "processed_rows",
        "error_message",
        "triggered_by",
    }
    assert expected_fields.issubset(set(TaskExecution.model_fields.keys()))


def test_task_definition_status_enum_values():
    expected_values = {"ACTIVE", "PAUSED", "CANCELLED"}
    assert expected_values.issubset({item.value for item in TaskDefinitionStatus})


def test_task_execution_status_enum_values():
    expected_values = {"QUEUED", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"}
    assert expected_values.issubset({item.value for item in TaskExecutionStatus})
