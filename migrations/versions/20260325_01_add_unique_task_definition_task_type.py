"""add unique task_definition task_type

Revision ID: 20260325_01
Revises: 20260317_01
Create Date: 2026-03-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260325_01"
down_revision: Union[str, Sequence[str], None] = "20260317_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_TASK_TYPE_INDEX = "ix_task_definitions_task_type"
UNIQUE_TASK_TYPE_INDEX = "ux_task_definitions_task_type"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "task_definitions" not in inspector.get_table_names():
        return
    task_definition_columns = {
        column["name"] for column in inspector.get_columns("task_definitions")
    }
    if "task_type" not in task_definition_columns:
        return
    task_definition_indexes = {
        item["name"] for item in inspector.get_indexes("task_definitions")
    }
    duplicate_rows = (
        conn.execute(
            sa.text(
                """
            SELECT task_type, COUNT(*) AS duplicate_count
            FROM task_definitions
            GROUP BY task_type
            HAVING COUNT(*) > 1
            ORDER BY task_type
            """
            )
        )
        .mappings()
        .all()
    )
    if duplicate_rows:
        duplicates = ", ".join(
            f"{row['task_type']} ({row['duplicate_count']})" for row in duplicate_rows
        )
        raise RuntimeError(
            "Duplicate task_definitions.task_type detected; "
            f"manual cleanup required before upgrade: {duplicates}"
        )

    if LEGACY_TASK_TYPE_INDEX in task_definition_indexes:
        op.drop_index(
            LEGACY_TASK_TYPE_INDEX,
            table_name="task_definitions",
        )
    if UNIQUE_TASK_TYPE_INDEX not in task_definition_indexes:
        op.create_index(
            UNIQUE_TASK_TYPE_INDEX,
            "task_definitions",
            ["task_type"],
            unique=True,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "task_definitions" not in inspector.get_table_names():
        return
    task_definition_columns = {
        column["name"] for column in inspector.get_columns("task_definitions")
    }
    if "task_type" not in task_definition_columns:
        return
    task_definition_indexes = {
        item["name"] for item in inspector.get_indexes("task_definitions")
    }
    if UNIQUE_TASK_TYPE_INDEX in task_definition_indexes:
        op.drop_index(UNIQUE_TASK_TYPE_INDEX, table_name="task_definitions")
    if LEGACY_TASK_TYPE_INDEX not in task_definition_indexes:
        op.create_index(
            LEGACY_TASK_TYPE_INDEX,
            "task_definitions",
            ["task_type"],
            unique=False,
        )
