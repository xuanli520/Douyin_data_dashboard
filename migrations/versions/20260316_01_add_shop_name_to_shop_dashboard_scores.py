"""add shop_name to shop_dashboard_scores

Revision ID: 20260316_01
Revises: 20260314_01
Create Date: 2026-03-16 10:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260316_01"
down_revision: Union[str, Sequence[str], None] = "20260314_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shop_dashboard_scores",
        sa.Column("shop_name", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shop_dashboard_scores", "shop_name")
