"""add_importstatus_enum_values

Revision ID: 6a799160424b
Revises: 690320e9dd97
Create Date: 2026-02-09 17:59:19.774212

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6a799160424b"
down_revision: Union[str, Sequence[str], None] = "690320e9dd97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add CANCELLED and VALIDATION_FAILED to importstatus enum.

    These values are used in data import cancellation and validation failure scenarios.
    """
    op.execute("ALTER TYPE importstatus ADD VALUE IF NOT EXISTS 'CANCELLED'")
    op.execute("ALTER TYPE importstatus ADD VALUE IF NOT EXISTS 'VALIDATION_FAILED'")


def downgrade() -> None:
    pass
