"""add agent_recipe table

Revision ID: 20260515_01
Revises: 20260325_01
Create Date: 2026-05-15 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260515_01"
down_revision: Union[str, Sequence[str], None] = "20260325_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("agent_recipes"):
        return

    op.create_table(
        "agent_recipes",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("namespace", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="active"
        ),
        sa.Column("entrypoint", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("observations", sa.JSON(), nullable=False),
        sa.Column("assertions", sa.JSON(), nullable=False),
        sa.Column("recovery_policy", sa.JSON(), nullable=False),
        sa.Column("security_policy", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "namespace",
            "key",
            "version",
            name="ux_agent_recipes_namespace_key_version",
        ),
    )
    op.create_index("ix_agent_recipes_namespace", "agent_recipes", ["namespace"])
    op.create_index("ix_agent_recipes_key", "agent_recipes", ["key"])
    op.create_index(
        "ix_agent_recipes_namespace_key_status_version",
        "agent_recipes",
        ["namespace", "key", "status", "version"],
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("agent_recipes"):
        return

    op.drop_index(
        "ix_agent_recipes_namespace_key_status_version",
        table_name="agent_recipes",
    )
    op.drop_index("ix_agent_recipes_key", table_name="agent_recipes")
    op.drop_index("ix_agent_recipes_namespace", table_name="agent_recipes")
    op.drop_table("agent_recipes")
