"""merge_heads

Revision ID: fc7a2b1
Revises: 25b889226314, 9f5f1dfe3a30
Create Date: 2026-01-29 17:20:00

"""

from typing import Union, Sequence


# revision identifiers, used by Alembic.
revision: str = "fc7a2b1"
down_revision: Union[str, Sequence[str]] = ("25b889226314", "9f5f1dfe3a30")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
