"""create task definition and execution tables

Revision ID: 60a123d3fa0a
Revises: 9f4e0f4e1d22
Create Date: 2026-03-08 23:42:20.225426

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "60a123d3fa0a"
down_revision: Union[str, Sequence[str], None] = "9f4e0f4e1d22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "task_definitions",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column(
            "task_type",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("schedule", sa.JSON(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_definitions_name"), "task_definitions", ["name"])
    op.create_index(
        op.f("ix_task_definitions_status"),
        "task_definitions",
        ["status"],
    )
    op.create_index(
        op.f("ix_task_definitions_task_type"),
        "task_definitions",
        ["task_type"],
    )
    op.create_index(
        "idx_task_definitions_task_type_status",
        "task_definitions",
        ["task_type", "status"],
    )

    op.create_table(
        "task_executions",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column(
            "queue_task_id",
            sqlmodel.sql.sqltypes.AutoString(length=100),
            nullable=True,
        ),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column(
            "trigger_mode",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_rows", sa.Integer(), nullable=False),
        sa.Column(
            "error_message",
            sqlmodel.sql.sqltypes.AutoString(length=1000),
            nullable=True,
        ),
        sa.Column("triggered_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["task_definitions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_task_executions_status"),
        "task_executions",
        ["status"],
    )
    op.create_index(
        "idx_task_executions_task_id_created_at",
        "task_executions",
        ["task_id", "created_at"],
    )
    op.create_index(
        "ux_task_executions_queue_task_id",
        "task_executions",
        ["queue_task_id"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ux_task_executions_queue_task_id", table_name="task_executions")
    op.drop_index(
        "idx_task_executions_task_id_created_at", table_name="task_executions"
    )
    op.drop_index(op.f("ix_task_executions_status"), table_name="task_executions")
    op.drop_table("task_executions")

    op.drop_index(
        "idx_task_definitions_task_type_status",
        table_name="task_definitions",
    )
    op.drop_index(op.f("ix_task_definitions_task_type"), table_name="task_definitions")
    op.drop_index(op.f("ix_task_definitions_status"), table_name="task_definitions")
    op.drop_index(op.f("ix_task_definitions_name"), table_name="task_definitions")
    op.drop_table("task_definitions")
