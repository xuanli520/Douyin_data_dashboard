"""add scraping_rules.version column

Revision ID: e3f1c8a9d2b7
Revises: b8f2e1a3c4d5
Create Date: 2026-03-11 11:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f1c8a9d2b7"
down_revision: Union[str, Sequence[str], None] = "b8f2e1a3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scraping_rules",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("scraping_rules", "version")
