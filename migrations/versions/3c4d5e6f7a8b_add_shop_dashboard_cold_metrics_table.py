"""add_shop_dashboard_cold_metrics_table

Revision ID: 3c4d5e6f7a8b
Revises: f2c51f6ed2a4
Create Date: 2026-03-06 15:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3c4d5e6f7a8b"
down_revision: Union[str, Sequence[str], None] = "f2c51f6ed2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shop_dashboard_cold_metrics",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.String(length=50), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("violations_detail", sa.JSON(), nullable=False),
        sa.Column("arbitration_detail", sa.JSON(), nullable=False),
        sa.Column("dsr_trend", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shop_id",
            "metric_date",
            "reason",
            name="uq_shop_dashboard_cold_metric_day_reason",
        ),
    )
    op.create_index(
        op.f("ix_shop_dashboard_cold_metrics_shop_id"),
        "shop_dashboard_cold_metrics",
        ["shop_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_shop_dashboard_cold_metrics_metric_date"),
        "shop_dashboard_cold_metrics",
        ["metric_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_shop_dashboard_cold_metrics_metric_date"),
        table_name="shop_dashboard_cold_metrics",
    )
    op.drop_index(
        op.f("ix_shop_dashboard_cold_metrics_shop_id"),
        table_name="shop_dashboard_cold_metrics",
    )
    op.drop_table("shop_dashboard_cold_metrics")
