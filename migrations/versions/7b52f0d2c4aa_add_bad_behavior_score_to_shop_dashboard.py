"""add_bad_behavior_score_to_shop_dashboard

Revision ID: 7b52f0d2c4aa
Revises: 27e8976139e6
Create Date: 2026-03-10 18:55:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7b52f0d2c4aa"
down_revision: Union[str, Sequence[str], None] = "27e8976139e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shop_dashboard_scores",
        sa.Column(
            "bad_behavior_score",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("shop_dashboard_scores", "bad_behavior_score")
