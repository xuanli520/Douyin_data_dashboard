"""contract drop datasource legacy fields

Revision ID: 20260310_02
Revises: c4f8d20e91a1
Create Date: 2026-03-11 21:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_02"
down_revision: Union[str, Sequence[str], None] = "c4f8d20e91a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.drop_index("ix_data_sources_shop_id")
        batch_op.drop_column("shop_id")
        batch_op.drop_column("account_name")


def downgrade() -> None:
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.add_column(
            sa.Column("account_name", sa.String(length=100), nullable=True)
        )
        batch_op.add_column(sa.Column("shop_id", sa.String(length=50), nullable=True))
        batch_op.create_index("ix_data_sources_shop_id", ["shop_id"], unique=False)
