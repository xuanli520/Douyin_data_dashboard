"""drop cookie health check collection jobs

Revision ID: 20260311_01
Revises: 20260310_02
Create Date: 2026-03-11 21:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_01"
down_revision: Union[str, Sequence[str], None] = "20260310_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("collection_jobs"):
        return
    collection_jobs = sa.table(
        "collection_jobs",
        sa.column("name", sa.String),
    )
    op.execute(
        sa.delete(collection_jobs).where(
            collection_jobs.c.name.like("shop-dashboard-cookie-health-check-%")
        )
    )


def downgrade() -> None:
    return None
