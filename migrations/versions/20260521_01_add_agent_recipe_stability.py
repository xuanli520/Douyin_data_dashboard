from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260521_01"
down_revision: Union[str, Sequence[str], None] = "20260515_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("agent_recipes"):
        return

    columns = {column["name"] for column in inspector.get_columns("agent_recipes")}
    if "stability" not in columns:
        op.add_column(
            "agent_recipes",
            sa.Column(
                "stability",
                sa.String(length=20),
                nullable=False,
                server_default="candidate",
            ),
        )

    indexes = {item["name"] for item in inspector.get_indexes("agent_recipes")}
    if "ix_agent_recipes_namespace_key_status_version" in indexes:
        op.drop_index(
            "ix_agent_recipes_namespace_key_status_version",
            table_name="agent_recipes",
        )
    if "ix_agent_recipes_namespace_key_status_stability_version" not in indexes:
        op.create_index(
            "ix_agent_recipes_namespace_key_status_stability_version",
            "agent_recipes",
            ["namespace", "key", "status", "stability", "version"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("agent_recipes"):
        return

    indexes = {item["name"] for item in inspector.get_indexes("agent_recipes")}
    if "ix_agent_recipes_namespace_key_status_stability_version" in indexes:
        op.drop_index(
            "ix_agent_recipes_namespace_key_status_stability_version",
            table_name="agent_recipes",
        )
    if "ix_agent_recipes_namespace_key_status_version" not in indexes:
        op.create_index(
            "ix_agent_recipes_namespace_key_status_version",
            "agent_recipes",
            ["namespace", "key", "status", "version"],
        )

    columns = {column["name"] for column in inspector.get_columns("agent_recipes")}
    if "stability" in columns:
        with op.batch_alter_table("agent_recipes") as batch_op:
            batch_op.drop_column("stability")
