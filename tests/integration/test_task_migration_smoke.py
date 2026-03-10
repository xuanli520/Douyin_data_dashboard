from sqlalchemy import inspect

from src.domains.task.models import TaskDefinition, TaskExecution

_ = (TaskDefinition, TaskExecution)


async def _collect_schema(session):
    connection = await session.connection()

    def _inspect(sync_conn):
        inspector = inspect(sync_conn)
        table_names = set(inspector.get_table_names())
        index_map = {
            table: inspector.get_indexes(table)
            for table in ("task_definitions", "task_executions")
        }
        return table_names, index_map

    return await connection.run_sync(_inspect)


async def test_task_tables_exist(test_db):
    async with test_db() as session:
        table_names, _ = await _collect_schema(session)

    assert "task_definitions" in table_names
    assert "task_executions" in table_names


async def test_task_indexes_exist(test_db):
    async with test_db() as session:
        _, index_map = await _collect_schema(session)

    task_definition_indexes = {item["name"] for item in index_map["task_definitions"]}
    task_execution_indexes = {item["name"] for item in index_map["task_executions"]}

    assert "idx_task_definitions_task_type_status" in task_definition_indexes
    assert "idx_task_executions_task_id_created_at" in task_execution_indexes
    assert "ux_task_executions_queue_task_id" in task_execution_indexes

    unique_flags = {
        item["name"]: bool(item.get("unique")) for item in index_map["task_executions"]
    }
    assert unique_flags["ux_task_executions_queue_task_id"] is True
