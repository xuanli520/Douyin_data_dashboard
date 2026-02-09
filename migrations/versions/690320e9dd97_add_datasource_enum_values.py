"""add_datasource_enum_values

Revision ID: 690320e9dd97
Revises: b17da509849c
Create Date: 2026-02-09 17:58:57.761301

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "690320e9dd97"
down_revision: Union[str, Sequence[str], None] = "b17da509849c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add DOUYIN_API and FILE_UPLOAD to datasourcetype enum.

    Fixes POST /api/v1/data-sources 500 error caused by missing enum values.
    """
    op.execute("ALTER TYPE datasourcetype ADD VALUE IF NOT EXISTS 'DOUYIN_API'")
    op.execute("ALTER TYPE datasourcetype ADD VALUE IF NOT EXISTS 'FILE_UPLOAD'")


def downgrade() -> None:
    pass
