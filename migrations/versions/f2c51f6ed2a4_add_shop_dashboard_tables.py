"""add_shop_dashboard_tables

Revision ID: f2c51f6ed2a4
Revises: ea189b5a72d8
Create Date: 2026-03-04 15:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2c51f6ed2a4"
down_revision: Union[str, Sequence[str], None] = "ea189b5a72d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shop_dashboard_scores",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.String(length=50), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=False),
        sa.Column("product_score", sa.Float(), nullable=False),
        sa.Column("logistics_score", sa.Float(), nullable=False),
        sa.Column("service_score", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_id", "metric_date", name="uq_shop_dashboard_score_day"),
    )
    op.create_index(
        op.f("ix_shop_dashboard_scores_metric_date"),
        "shop_dashboard_scores",
        ["metric_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_shop_dashboard_scores_shop_id"),
        "shop_dashboard_scores",
        ["shop_id"],
        unique=False,
    )

    op.create_table(
        "shop_dashboard_reviews",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.String(length=50), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("review_id", sa.String(length=100), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("is_replied", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shop_id",
            "metric_date",
            "review_id",
            name="uq_shop_dashboard_review_day",
        ),
    )
    op.create_index(
        op.f("ix_shop_dashboard_reviews_metric_date"),
        "shop_dashboard_reviews",
        ["metric_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_shop_dashboard_reviews_shop_id"),
        "shop_dashboard_reviews",
        ["shop_id"],
        unique=False,
    )

    op.create_table(
        "shop_dashboard_violations",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.String(length=50), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("violation_id", sa.String(length=100), nullable=False),
        sa.Column("violation_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shop_id",
            "metric_date",
            "violation_id",
            name="uq_shop_dashboard_violation_day",
        ),
    )
    op.create_index(
        op.f("ix_shop_dashboard_violations_metric_date"),
        "shop_dashboard_violations",
        ["metric_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_shop_dashboard_violations_shop_id"),
        "shop_dashboard_violations",
        ["shop_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_shop_dashboard_violations_shop_id"),
        table_name="shop_dashboard_violations",
    )
    op.drop_index(
        op.f("ix_shop_dashboard_violations_metric_date"),
        table_name="shop_dashboard_violations",
    )
    op.drop_table("shop_dashboard_violations")

    op.drop_index(
        op.f("ix_shop_dashboard_reviews_shop_id"),
        table_name="shop_dashboard_reviews",
    )
    op.drop_index(
        op.f("ix_shop_dashboard_reviews_metric_date"),
        table_name="shop_dashboard_reviews",
    )
    op.drop_table("shop_dashboard_reviews")

    op.drop_index(
        op.f("ix_shop_dashboard_scores_shop_id"),
        table_name="shop_dashboard_scores",
    )
    op.drop_index(
        op.f("ix_shop_dashboard_scores_metric_date"),
        table_name="shop_dashboard_scores",
    )
    op.drop_table("shop_dashboard_scores")
