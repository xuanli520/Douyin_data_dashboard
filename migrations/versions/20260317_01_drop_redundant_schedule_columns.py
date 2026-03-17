"""drop redundant schedule columns

Revision ID: 20260317_01
Revises: 20260316_02
Create Date: 2026-03-17 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260317_01"
down_revision: Union[str, Sequence[str], None] = "20260316_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return column_name in {
        column["name"] for column in inspector.get_columns(table_name)
    }


def upgrade() -> None:
    if _has_column("scraping_rules", "schedule"):
        with op.batch_alter_table("scraping_rules") as batch_op:
            batch_op.drop_column("schedule")

    if _has_column("task_definitions", "schedule"):
        with op.batch_alter_table("task_definitions") as batch_op:
            batch_op.drop_column("schedule")


def downgrade() -> None:
    if not _has_column("scraping_rules", "schedule"):
        with op.batch_alter_table("scraping_rules") as batch_op:
            batch_op.add_column(sa.Column("schedule", sa.JSON(), nullable=True))

    if not _has_column("task_definitions", "schedule"):
        with op.batch_alter_table("task_definitions") as batch_op:
            batch_op.add_column(sa.Column("schedule", sa.JSON(), nullable=True))
