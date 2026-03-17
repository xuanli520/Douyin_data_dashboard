"""fix_user_stats_and_audit_fields

Revision ID: 06038dbc9807
Revises: 6a799160424b
Create Date: 2026-02-09 19:20:50.932208

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "06038dbc9807"
down_revision: Union[str, Sequence[str], None] = "6a799160424b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("audit_logs")}
    index_name = op.f("ix_audit_logs_action")
    if index_name not in existing_indexes:
        op.create_index(index_name, "audit_logs", ["action"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    pass
