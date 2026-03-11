"""add_experience_metrics_tables

Revision ID: b8f2e1a3c4d5
Revises: 9f4e0f4e1d22
Create Date: 2026-03-10 19:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b8f2e1a3c4d5"
down_revision: Union[str, Sequence[str], None] = "9f4e0f4e1d22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "experience_metric_daily",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.String(length=50), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("dimension", sa.String(length=30), nullable=False),
        sa.Column("metric_key", sa.String(length=80), nullable=False),
        sa.Column("metric_score", sa.Float(), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("metric_unit", sa.String(length=16), nullable=False),
        sa.Column("source_field", sa.String(length=128), nullable=False),
        sa.Column("formula_expr", sa.String(length=255), nullable=True),
        sa.Column("is_penalty", sa.Boolean(), nullable=False),
        sa.Column("deduct_points", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shop_id",
            "metric_date",
            "dimension",
            "metric_key",
            name="uq_experience_metric_daily_shop_day_dimension_metric",
        ),
    )
    op.create_index(
        op.f("ix_experience_metric_daily_shop_id"),
        "experience_metric_daily",
        ["shop_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_experience_metric_daily_metric_date"),
        "experience_metric_daily",
        ["metric_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_experience_metric_daily_dimension"),
        "experience_metric_daily",
        ["dimension"],
        unique=False,
    )
    op.create_index(
        op.f("ix_experience_metric_daily_metric_key"),
        "experience_metric_daily",
        ["metric_key"],
        unique=False,
    )
    op.create_index(
        "ix_experience_metric_daily_shop_metric_date",
        "experience_metric_daily",
        ["shop_id", "metric_date"],
        unique=False,
    )
    op.create_index(
        "ix_experience_metric_daily_shop_dimension_metric_date",
        "experience_metric_daily",
        ["shop_id", "dimension", "metric_date"],
        unique=False,
    )

    op.create_table(
        "experience_issue_daily",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.String(length=50), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("dimension", sa.String(length=30), nullable=False),
        sa.Column("issue_key", sa.String(length=100), nullable=False),
        sa.Column("issue_title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("owner", sa.String(length=60), nullable=False),
        sa.Column("impact_score", sa.Float(), nullable=False),
        sa.Column("deduct_points", sa.Float(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shop_id",
            "metric_date",
            "issue_key",
            name="uq_experience_issue_daily_shop_day_issue",
        ),
    )
    op.create_index(
        op.f("ix_experience_issue_daily_shop_id"),
        "experience_issue_daily",
        ["shop_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_experience_issue_daily_metric_date"),
        "experience_issue_daily",
        ["metric_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_experience_issue_daily_dimension"),
        "experience_issue_daily",
        ["dimension"],
        unique=False,
    )
    op.create_index(
        op.f("ix_experience_issue_daily_status"),
        "experience_issue_daily",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_experience_issue_daily_shop_metric_date",
        "experience_issue_daily",
        ["shop_id", "metric_date"],
        unique=False,
    )
    op.create_index(
        "ix_experience_issue_daily_shop_dimension_metric_date",
        "experience_issue_daily",
        ["shop_id", "dimension", "metric_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_experience_issue_daily_shop_dimension_metric_date",
        table_name="experience_issue_daily",
    )
    op.drop_index(
        "ix_experience_issue_daily_shop_metric_date",
        table_name="experience_issue_daily",
    )
    op.drop_index(
        op.f("ix_experience_issue_daily_status"),
        table_name="experience_issue_daily",
    )
    op.drop_index(
        op.f("ix_experience_issue_daily_dimension"),
        table_name="experience_issue_daily",
    )
    op.drop_index(
        op.f("ix_experience_issue_daily_metric_date"),
        table_name="experience_issue_daily",
    )
    op.drop_index(
        op.f("ix_experience_issue_daily_shop_id"),
        table_name="experience_issue_daily",
    )
    op.drop_table("experience_issue_daily")

    op.drop_index(
        "ix_experience_metric_daily_shop_dimension_metric_date",
        table_name="experience_metric_daily",
    )
    op.drop_index(
        "ix_experience_metric_daily_shop_metric_date",
        table_name="experience_metric_daily",
    )
    op.drop_index(
        op.f("ix_experience_metric_daily_metric_key"),
        table_name="experience_metric_daily",
    )
    op.drop_index(
        op.f("ix_experience_metric_daily_dimension"),
        table_name="experience_metric_daily",
    )
    op.drop_index(
        op.f("ix_experience_metric_daily_metric_date"),
        table_name="experience_metric_daily",
    )
    op.drop_index(
        op.f("ix_experience_metric_daily_shop_id"),
        table_name="experience_metric_daily",
    )
    op.drop_table("experience_metric_daily")
