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
    duplicate_rows = conn.execute(
        sa.text(
            """
            SELECT id, keep_id
            FROM (
                SELECT
                    id,
                    task_type,
                    MIN(id) OVER (PARTITION BY task_type) AS keep_id
                FROM task_definitions
            ) ranked
            WHERE id <> keep_id
            ORDER BY id
            """
        )
    ).mappings()

    for row in duplicate_rows:
        conn.execute(
            sa.text(
                """
                UPDATE task_executions
                SET task_id = :keep_id
                WHERE task_id = :task_id
                """
            ),
            {"keep_id": row["keep_id"], "task_id": row["id"]},
        )
        conn.execute(
            sa.text("DELETE FROM task_definitions WHERE id = :task_id"),
            {"task_id": row["id"]},
        )

    if op.f("ix_task_definitions_task_type") in task_definition_indexes:
        op.drop_index(
            op.f("ix_task_definitions_task_type"),
            table_name="task_definitions",
        )
    if "ux_task_definitions_task_type" not in task_definition_indexes:
        op.create_index(
            "ux_task_definitions_task_type",
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
    if "ux_task_definitions_task_type" in task_definition_indexes:
        op.drop_index("ux_task_definitions_task_type", table_name="task_definitions")
    if op.f("ix_task_definitions_task_type") not in task_definition_indexes:
        op.create_index(
            op.f("ix_task_definitions_task_type"),
            "task_definitions",
            ["task_type"],
            unique=False,
        )
