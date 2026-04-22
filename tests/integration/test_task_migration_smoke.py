import os
import tempfile
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, inspect, text

from src.config import get_settings
from src.domains.collection_job.models import CollectionJob
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.task.models import TaskDefinition, TaskExecution

_ = (CollectionJob, DataSource, ScrapingRule, TaskDefinition, TaskExecution)


@contextmanager
def _temp_sqlite_db(root: Path, prefix: str):
    fd, temp_name = tempfile.mkstemp(prefix=f"{prefix}-", suffix=".db", dir=root)
    os.close(fd)
    db_path = Path(temp_name)
    try:
        yield db_path
    finally:
        db_path.unlink(missing_ok=True)


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

    assert "ux_task_definitions_task_type" in task_definition_indexes
    assert "idx_task_definitions_task_type_status" in task_definition_indexes
    assert "idx_task_executions_task_id_created_at" in task_execution_indexes
    assert "ux_task_executions_queue_task_id" in task_execution_indexes
    assert "ux_task_executions_idempotency_key" in task_execution_indexes

    unique_flags = {
        item["name"]: bool(item.get("unique")) for item in index_map["task_definitions"]
    }
    assert unique_flags["ux_task_definitions_task_type"] is True
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


def test_contract_migration_executes_through_alembic(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    with _temp_sqlite_db(root, "contract_migration_smoke") as db_path:
        sqlite_url = str(db_path).replace("\\", "/")

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
        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                data_source_columns = {
                    column["name"] for column in inspector.get_columns("data_sources")
                }
                scraping_rule_columns = {
                    column["name"] for column in inspector.get_columns("scraping_rules")
                }
                task_definition_columns = {
                    column["name"]
                    for column in inspector.get_columns("task_definitions")
                }
                version_num = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
        finally:
            engine.dispose()

        assert "shop_id" not in data_source_columns
        assert "account_name" not in data_source_columns
        assert "schedule" not in scraping_rule_columns
        assert "schedule" not in task_definition_columns
        assert version_num == expected_head


def test_unique_task_type_migration_rejects_duplicate_definitions(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    with _temp_sqlite_db(root, "duplicate_task_type_migration") as db_path:
        sqlite_url = str(db_path).replace("\\", "/")

        connection = sqlite3.connect(db_path)
        try:
            connection.executescript(
                """
                CREATE TABLE task_definitions (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    task_type VARCHAR(100) NOT NULL,
                    status VARCHAR(50),
                    config TEXT,
                    created_by_id INTEGER,
                    updated_by_id INTEGER,
                    created_at DATETIME,
                    updated_at DATETIME
                );
                CREATE INDEX ix_task_definitions_task_type
                ON task_definitions (task_type);
                CREATE TABLE task_executions (
                    id INTEGER PRIMARY KEY,
                    task_id INTEGER NOT NULL,
                    created_at DATETIME
                );
                INSERT INTO task_definitions (
                    id,
                    name,
                    task_type,
                    status,
                    config,
                    created_at,
                    updated_at
                ) VALUES
                    (
                        1,
                        'primary dashboard task',
                        'SHOP_DASHBOARD_COLLECTION',
                        'ACTIVE',
                        '{"window":"primary"}',
                        '2026-03-17T00:00:00',
                        '2026-03-17T00:00:00'
                    ),
                    (
                        2,
                        'secondary dashboard task',
                        'SHOP_DASHBOARD_COLLECTION',
                        'DISABLED',
                        '{"window":"secondary"}',
                        '2026-03-17T00:00:00',
                        '2026-03-17T00:00:00'
                    );
                INSERT INTO task_executions (id, task_id, created_at) VALUES
                    (11, 1, '2026-03-17T00:00:00'),
                    (12, 2, '2026-03-17T00:00:00');
                CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
                INSERT INTO alembic_version (version_num) VALUES ('20260317_01');
                """
            )
            connection.commit()
        finally:
            connection.close()

        monkeypatch.setenv("DB__DRIVER", "sqlite")
        monkeypatch.setenv("DB__DATABASE", sqlite_url)
        get_settings.cache_clear()
        try:
            config = Config(str(root / "alembic.ini"))
            with pytest.raises(
                RuntimeError,
                match="Duplicate task_definitions.task_type",
            ):
                command.upgrade(config, "head")
        finally:
            get_settings.cache_clear()

        engine = create_engine(f"sqlite:///{sqlite_url}")
        try:
            with engine.connect() as conn:
                task_definition_rows = (
                    conn.execute(
                        text(
                            """
                        SELECT id, name, task_type, status, config
                        FROM task_definitions
                        ORDER BY id
                        """
                        )
                    )
                    .mappings()
                    .all()
                )
                task_execution_rows = (
                    conn.execute(
                        text(
                            """
                        SELECT id, task_id
                        FROM task_executions
                        ORDER BY id
                        """
                        )
                    )
                    .mappings()
                    .all()
                )
                version_num = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
        finally:
            engine.dispose()

        assert [row["id"] for row in task_definition_rows] == [1, 2]
        assert [row["task_id"] for row in task_execution_rows] == [1, 2]
        assert version_num == "20260317_01"


def test_audit_logs_action_index_round_trips_on_single_step_downgrade(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    with _temp_sqlite_db(root, "audit_logs_action_index") as db_path:
        sqlite_url = str(db_path).replace("\\", "/")

        connection = sqlite3.connect(db_path)
        try:
            connection.executescript(
                """
                CREATE TABLE audit_logs (
                    id INTEGER PRIMARY KEY,
                    action VARCHAR(100)
                );
                CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
                INSERT INTO alembic_version (version_num) VALUES ('6a799160424b');
                """
            )
            connection.commit()
        finally:
            connection.close()

        monkeypatch.setenv("DB__DRIVER", "sqlite")
        monkeypatch.setenv("DB__DATABASE", sqlite_url)
        get_settings.cache_clear()
        try:
            config = Config(str(root / "alembic.ini"))
            command.upgrade(config, "06038dbc9807")
            engine = create_engine(f"sqlite:///{sqlite_url}")
            try:
                with engine.connect() as conn:
                    inspector = inspect(conn)
                    upgraded_indexes = {
                        item["name"] for item in inspector.get_indexes("audit_logs")
                    }
            finally:
                engine.dispose()
            assert "ix_audit_logs_action" in upgraded_indexes

            command.downgrade(config, "6a799160424b")
        finally:
            get_settings.cache_clear()

        engine = create_engine(f"sqlite:///{sqlite_url}")
        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                downgraded_indexes = {
                    item["name"] for item in inspector.get_indexes("audit_logs")
                }
                version_num = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
        finally:
            engine.dispose()

    assert "ix_audit_logs_action" not in downgraded_indexes
    assert version_num == "6a799160424b"


def test_init_downgrade_tolerates_missing_audit_logs_action_index(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    with _temp_sqlite_db(root, "init_downgrade_missing_audit_index") as db_path:
        sqlite_url = str(db_path).replace("\\", "/")

        connection = sqlite3.connect(db_path)
        try:
            connection.executescript(
                """
                CREATE TABLE permissions (
                    id INTEGER PRIMARY KEY,
                    code VARCHAR(150),
                    name VARCHAR(100),
                    description VARCHAR(255),
                    module VARCHAR(100),
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                );
                CREATE UNIQUE INDEX ix_permissions_code ON permissions (code);

                CREATE TABLE roles (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100),
                    description VARCHAR(255),
                    is_system BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                );
                CREATE UNIQUE INDEX ix_roles_name ON roles (name);

                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(50),
                    email VARCHAR(320),
                    hashed_password VARCHAR(1024),
                    is_active BOOLEAN NOT NULL,
                    is_superuser BOOLEAN NOT NULL,
                    is_verified BOOLEAN NOT NULL,
                    gender VARCHAR(20),
                    phone VARCHAR(20),
                    department VARCHAR(100),
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                );
                CREATE UNIQUE INDEX ix_users_email ON users (email);
                CREATE UNIQUE INDEX ix_users_username ON users (username);

                CREATE TABLE audit_logs (
                    id INTEGER PRIMARY KEY,
                    occurred_at DATETIME NOT NULL,
                    request_id VARCHAR(36),
                    actor_id INTEGER,
                    action VARCHAR(64) NOT NULL,
                    resource_type VARCHAR(64),
                    resource_id TEXT,
                    result VARCHAR(32) NOT NULL,
                    user_agent TEXT,
                    ip VARCHAR(45),
                    extra TEXT,
                    FOREIGN KEY(actor_id) REFERENCES users(id) ON DELETE SET NULL
                );
                CREATE INDEX ix_audit_logs_actor_id ON audit_logs (actor_id);
                CREATE INDEX ix_audit_logs_occurred_at ON audit_logs (occurred_at);

                CREATE TABLE oauth_accounts (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    oauth_name VARCHAR(100) NOT NULL,
                    access_token VARCHAR(1024) NOT NULL,
                    expires_at INTEGER,
                    refresh_token VARCHAR(1024),
                    account_id VARCHAR(320) NOT NULL,
                    account_email VARCHAR(320) NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                CREATE INDEX ix_oauth_accounts_account_id
                ON oauth_accounts (account_id);
                CREATE INDEX ix_oauth_accounts_oauth_name
                ON oauth_accounts (oauth_name);
                CREATE INDEX ix_oauth_accounts_user_id
                ON oauth_accounts (user_id);

                CREATE TABLE role_permissions (
                    role_id INTEGER NOT NULL,
                    permission_id INTEGER NOT NULL,
                    assigned_at DATETIME NOT NULL,
                    PRIMARY KEY (role_id, permission_id),
                    FOREIGN KEY(role_id) REFERENCES roles(id),
                    FOREIGN KEY(permission_id) REFERENCES permissions(id)
                );

                CREATE TABLE user_roles (
                    user_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    assigned_at DATETIME NOT NULL,
                    PRIMARY KEY (user_id, role_id),
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(role_id) REFERENCES roles(id)
                );

                CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
                INSERT INTO alembic_version (version_num) VALUES ('000000000000');
                """
            )
            connection.commit()
        finally:
            connection.close()

        monkeypatch.setenv("DB__DRIVER", "sqlite")
        monkeypatch.setenv("DB__DATABASE", sqlite_url)
        get_settings.cache_clear()
        try:
            config = Config(str(root / "alembic.ini"))
            command.downgrade(config, "base")
        finally:
            get_settings.cache_clear()

        engine = create_engine(f"sqlite:///{sqlite_url}")
        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                remaining_tables = set(inspector.get_table_names())
        finally:
            engine.dispose()

        assert "audit_logs" not in remaining_tables
        assert "users" not in remaining_tables
