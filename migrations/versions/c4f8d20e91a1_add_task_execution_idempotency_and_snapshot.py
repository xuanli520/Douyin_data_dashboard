"""add task execution idempotency and snapshot fields

Revision ID: c4f8d20e91a1
Revises: f4d5c6b7a8e9
Create Date: 2026-03-11 16:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f8d20e91a1"
down_revision: Union[str, Sequence[str], None] = "f4d5c6b7a8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task_executions",
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "task_executions",
        sa.Column("rule_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "task_executions",
        sa.Column("effective_config_snapshot", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ux_task_executions_idempotency_key",
        "task_executions",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_task_executions_idempotency_key", table_name="task_executions")
    op.drop_column("task_executions", "effective_config_snapshot")
    op.drop_column("task_executions", "rule_version")
    op.drop_column("task_executions", "idempotency_key")
