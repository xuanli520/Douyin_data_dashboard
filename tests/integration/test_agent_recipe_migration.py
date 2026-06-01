import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from src.domains.agent_recipe.models import AgentRecipe

_ = (AgentRecipe,)


@contextmanager
def _temp_sqlite_db(root: Path, prefix: str):
    fd, temp_name = tempfile.mkstemp(prefix=f"{prefix}-", suffix=".db", dir=root)
    os.close(fd)
    db_path = Path(temp_name)
    try:
        yield db_path
    finally:
        db_path.unlink(missing_ok=True)


async def test_agent_recipe_table_exists(test_db):
    async with test_db() as session:
        connection = await session.connection()

        def _inspect(sync_conn):
            inspector = inspect(sync_conn)
            table_names = set(inspector.get_table_names())
            columns = {
                column["name"] for column in inspector.get_columns("agent_recipes")
            }
            indexes = {
                item["name"]: bool(item.get("unique"))
                for item in inspector.get_indexes("agent_recipes")
            }
            return table_names, columns, indexes

        table_names, columns, indexes = await connection.run_sync(_inspect)

    assert "agent_recipes" in table_names
    assert columns == {
        "id",
        "namespace",
        "key",
        "version",
        "status",
        "stability",
        "entrypoint",
        "steps",
        "observations",
        "assertions",
        "recovery_policy",
        "security_policy",
        "created_at",
        "updated_at",
    }
    assert "ix_agent_recipes_namespace" in indexes
    assert "ix_agent_recipes_key" in indexes
    assert "ix_agent_recipes_namespace_key_status_stability_version" in indexes


def test_agent_recipe_migration_upgrade_and_downgrade(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    with _temp_sqlite_db(root, "agent_recipe_migration") as db_path:
        sqlite_url = str(db_path).replace("\\", "/")

        connection = sqlite3.connect(db_path)
        try:
            connection.execute(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
            )
            connection.execute(
                "INSERT INTO alembic_version (version_num) VALUES ('20260325_01')"
            )
            connection.commit()
        finally:
            connection.close()

        monkeypatch.setenv("DB__DRIVER", "sqlite")
        monkeypatch.setenv("DB__DATABASE", sqlite_url)
        from src.config import get_settings

        get_settings.cache_clear()
        try:
            config = Config(str(root / "alembic.ini"))
            command.upgrade(config, "head")

            engine = create_engine(f"sqlite:///{sqlite_url}")
            try:
                with engine.connect() as conn:
                    inspector = inspect(conn)
                    table_names = set(inspector.get_table_names())
                    columns = {
                        column["name"]
                        for column in inspector.get_columns("agent_recipes")
                    }
                    index_names = {
                        item["name"] for item in inspector.get_indexes("agent_recipes")
                    }
                    unique_constraints = {
                        item["name"]
                        for item in inspector.get_unique_constraints("agent_recipes")
                    }
            finally:
                engine.dispose()

            assert "agent_recipes" in table_names
            assert "status" in columns
            assert "stability" in columns
            assert "ux_agent_recipes_namespace_key_version" in unique_constraints
            assert (
                "ix_agent_recipes_namespace_key_status_stability_version" in index_names
            )

            command.downgrade(config, "20260325_01")
        finally:
            get_settings.cache_clear()

        engine = create_engine(f"sqlite:///{sqlite_url}")
        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                remaining_tables = set(inspector.get_table_names())
        finally:
            engine.dispose()

    assert "agent_recipes" not in remaining_tables
