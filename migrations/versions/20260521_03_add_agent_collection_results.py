"""add agent collection results table

Revision ID: 20260521_03
Revises: 20260521_02
Create Date: 2026-05-21 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260521_03"
down_revision: Union[str, Sequence[str], None] = "20260521_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE_NAME = "agent_collection_results"
_UNIQUE_NAME = "ux_agent_collection_result"
_UNIQUE_COLUMNS = ["namespace", "resource_key", "resource_date"]


def _unique_constraint_exists(conn: sa.Connection) -> bool:
    inspector = sa.inspect(conn)
    for item in inspector.get_unique_constraints(_TABLE_NAME):
        if item.get("name") == _UNIQUE_NAME:
            return True
        if item.get("column_names") == _UNIQUE_COLUMNS:
            return True
    for item in inspector.get_indexes(_TABLE_NAME):
        if not item.get("unique"):
            continue
        if item.get("name") == _UNIQUE_NAME:
            return True
        if item.get("column_names") == _UNIQUE_COLUMNS:
            return True
    return False


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(_TABLE_NAME):
        op.create_table(
            _TABLE_NAME,
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("namespace", sa.String(length=100), nullable=False),
            sa.Column("resource_key", sa.String(length=200), nullable=False),
            sa.Column("resource_date", sa.Date(), nullable=False),
            sa.Column("recipe_id", sa.Integer(), nullable=False),
            sa.Column("output", sa.JSON(), nullable=False),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="success",
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["recipe_id"], ["agent_recipes.id"]),
            sa.UniqueConstraint(
                "namespace",
                "resource_key",
                "resource_date",
                name=_UNIQUE_NAME,
            ),
        )
        op.create_index(
            "ix_agent_collection_results_namespace",
            _TABLE_NAME,
            ["namespace"],
        )
        op.create_index(
            "ix_agent_collection_results_resource_key",
            _TABLE_NAME,
            ["resource_key"],
        )
        op.create_index(
            "ix_agent_collection_results_resource_date",
            _TABLE_NAME,
            ["resource_date"],
        )
        return

    if not _unique_constraint_exists(conn):
        if conn.dialect.name == "sqlite":
            op.create_index(_UNIQUE_NAME, _TABLE_NAME, _UNIQUE_COLUMNS, unique=True)
        else:
            op.create_unique_constraint(_UNIQUE_NAME, _TABLE_NAME, _UNIQUE_COLUMNS)

    index_names = {index["name"] for index in inspector.get_indexes(_TABLE_NAME)}
    if "ix_agent_collection_results_namespace" not in index_names:
        op.create_index(
            "ix_agent_collection_results_namespace",
            _TABLE_NAME,
            ["namespace"],
        )
    if "ix_agent_collection_results_resource_key" not in index_names:
        op.create_index(
            "ix_agent_collection_results_resource_key",
            _TABLE_NAME,
            ["resource_key"],
        )
    if "ix_agent_collection_results_resource_date" not in index_names:
        op.create_index(
            "ix_agent_collection_results_resource_date",
            _TABLE_NAME,
            ["resource_date"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(_TABLE_NAME):
        return

    index_names = {index["name"] for index in inspector.get_indexes(_TABLE_NAME)}
    for index_name in (
        "ix_agent_collection_results_resource_date",
        "ix_agent_collection_results_resource_key",
        "ix_agent_collection_results_namespace",
    ):
        if index_name in index_names:
            op.drop_index(index_name, table_name=_TABLE_NAME)
    op.drop_table(_TABLE_NAME)
