"""add_scraping_rule_extra_config

Revision ID: be16395279bd
Revises: 8e9cd22532a3
Create Date: 2026-02-09 17:45:48.985461

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "be16395279bd"
down_revision: Union[str, Sequence[str], None] = "8e9cd22532a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("scraping_rules", sa.Column("extra_config", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("scraping_rules", "extra_config")
