import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from src.config import get_settings
from src.domains.collection_job.models import CollectionJob
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.task.models import TaskDefinition, TaskExecution

_ = (CollectionJob, DataSource, ScrapingRule, TaskDefinition, TaskExecution)


async def _collect_schema(session):
    connection = await session.connection()

    def _inspect(sync_conn):
        inspector = inspect(sync_conn)
        table_names = set(inspector.get_table_names())
        index_map = {
            table: inspector.get_indexes(table)
            for table in ("task_definitions", "task_executions")
        }
        data_source_columns = {
            column["name"] for column in inspector.get_columns("data_sources")
        }
        scraping_rule_columns = {
            column["name"] for column in inspector.get_columns("scraping_rules")
        }
        task_definition_columns = {
            column["name"] for column in inspector.get_columns("task_definitions")
        }
        return (
            table_names,
            index_map,
            data_source_columns,
            scraping_rule_columns,
            task_definition_columns,
        )

    return await connection.run_sync(_inspect)


async def test_task_tables_exist(test_db):
    async with test_db() as session:
        table_names, _, _, _, _ = await _collect_schema(session)

    assert "task_definitions" in table_names
    assert "task_executions" in table_names
    assert "collection_jobs" in table_names


async def test_task_indexes_exist(test_db):
    async with test_db() as session:
        _, index_map, _, _, _ = await _collect_schema(session)

    task_definition_indexes = {item["name"] for item in index_map["task_definitions"]}
    task_execution_indexes = {item["name"] for item in index_map["task_executions"]}

    assert "idx_task_definitions_task_type_status" in task_definition_indexes
    assert "idx_task_executions_task_id_created_at" in task_execution_indexes
    assert "ux_task_executions_queue_task_id" in task_execution_indexes
    assert "ux_task_executions_idempotency_key" in task_execution_indexes

    unique_flags = {
        item["name"]: bool(item.get("unique")) for item in index_map["task_executions"]
    }
    assert unique_flags["ux_task_executions_queue_task_id"] is True
    assert unique_flags["ux_task_executions_idempotency_key"] is True


async def test_data_sources_legacy_columns_removed(test_db):
    async with test_db() as session:
        _, _, data_source_columns, _, _ = await _collect_schema(session)

    assert "shop_id" not in data_source_columns
    assert "account_name" not in data_source_columns


async def test_schedule_columns_removed(test_db):
    async with test_db() as session:
        _, _, _, scraping_rule_columns, task_definition_columns = await _collect_schema(
            session
        )

    assert "schedule" not in scraping_rule_columns
    assert "schedule" not in task_definition_columns


def test_contract_migration_executes_through_alembic(tmp_path, monkeypatch):
    db_path = tmp_path / "contract_migration_smoke.db"
    sqlite_url = str(db_path).replace("\\", "/")
    root = Path(__file__).resolve().parents[2]

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE data_sources (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100),
                shop_id VARCHAR(50),
                account_name VARCHAR(100),
                extra_config TEXT
            )
            """
        )
        connection.execute(
            "CREATE INDEX ix_data_sources_shop_id ON data_sources (shop_id)"
        )
        connection.execute(
            """
            CREATE TABLE scraping_rules (
                id INTEGER PRIMARY KEY,
                schedule TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE task_definitions (
                id INTEGER PRIMARY KEY,
                schedule TEXT
            )
            """
        )
        connection.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES ('c4f8d20e91a1')"
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setenv("DB__DRIVER", "sqlite")
    monkeypatch.setenv("DB__DATABASE", sqlite_url)
    get_settings.cache_clear()
    try:
        config = Config(str(root / "alembic.ini"))
        expected_head = ScriptDirectory.from_config(config).get_current_head()
        command.upgrade(config, "head")
    finally:
        get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{sqlite_url}")
    with engine.connect() as conn:
        inspector = inspect(conn)
        data_source_columns = {
            column["name"] for column in inspector.get_columns("data_sources")
        }
        scraping_rule_columns = {
            column["name"] for column in inspector.get_columns("scraping_rules")
        }
        task_definition_columns = {
            column["name"] for column in inspector.get_columns("task_definitions")
        }
        version_num = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()

    assert "shop_id" not in data_source_columns
    assert "account_name" not in data_source_columns
    assert "schedule" not in scraping_rule_columns
    assert "schedule" not in task_definition_columns
    assert version_num == expected_head
