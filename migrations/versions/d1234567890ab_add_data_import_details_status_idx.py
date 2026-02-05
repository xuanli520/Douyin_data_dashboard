"""add data_import_details composite index on (import_record_id, status)

Revision ID: d1234567890ab
Revises: c1234567890ab
Create Date: 2026-02-05 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "d1234567890ab"
down_revision: Union[str, Sequence[str], None] = "c1234567890ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_data_import_details_record_status"),
        "data_import_details",
        ["import_record_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_data_import_details_record_status"),
        table_name="data_import_details",
    )
