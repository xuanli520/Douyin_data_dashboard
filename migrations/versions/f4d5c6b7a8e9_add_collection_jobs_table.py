"""add collection_jobs table

Revision ID: f4d5c6b7a8e9
Revises: e3f1c8a9d2b7
Create Date: 2026-03-11 13:20:00.000000

"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4d5c6b7a8e9"
down_revision: Union[str, Sequence[str], None] = "e3f1c8a9d2b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collection_jobs",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_id"], ["data_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["scraping_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collection_jobs_name", "collection_jobs", ["name"])
    op.create_index(
        "ix_collection_jobs_task_type",
        "collection_jobs",
        ["task_type"],
    )
    op.create_index(
        "ix_collection_jobs_data_source_id",
        "collection_jobs",
        ["data_source_id"],
    )
    op.create_index("ix_collection_jobs_rule_id", "collection_jobs", ["rule_id"])
    op.create_index("ix_collection_jobs_status", "collection_jobs", ["status"])
    op.create_index(
        "idx_collection_jobs_task_type_status",
        "collection_jobs",
        ["task_type", "status"],
    )

    _backfill_collection_jobs()


def downgrade() -> None:
    op.drop_index("idx_collection_jobs_task_type_status", table_name="collection_jobs")
    op.drop_index("ix_collection_jobs_status", table_name="collection_jobs")
    op.drop_index("ix_collection_jobs_rule_id", table_name="collection_jobs")
    op.drop_index("ix_collection_jobs_data_source_id", table_name="collection_jobs")
    op.drop_index("ix_collection_jobs_task_type", table_name="collection_jobs")
    op.drop_index("ix_collection_jobs_name", table_name="collection_jobs")
    op.drop_table("collection_jobs")


def _backfill_collection_jobs() -> None:
    bind = op.get_bind()
    scraping_rules = sa.table(
        "scraping_rules",
        sa.column("id", sa.Integer),
        sa.column("data_source_id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("timezone", sa.String),
        sa.column("granularity", sa.String),
        sa.column("incremental_mode", sa.String),
        sa.column("data_latency", sa.String),
    )
    data_sources = sa.table(
        "data_sources",
        sa.column("id", sa.Integer),
        sa.column("status", sa.String),
    )
    collection_jobs = sa.table(
        "collection_jobs",
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("name", sa.String),
        sa.column("task_type", sa.String),
        sa.column("data_source_id", sa.Integer),
        sa.column("rule_id", sa.Integer),
        sa.column("schedule", sa.JSON),
        sa.column("status", sa.String),
    )

    rows = bind.execute(
        sa.select(
            scraping_rules.c.id,
            scraping_rules.c.data_source_id,
            scraping_rules.c.timezone,
            scraping_rules.c.granularity,
            scraping_rules.c.incremental_mode,
            scraping_rules.c.data_latency,
        )
        .select_from(
            scraping_rules.join(
                data_sources,
                scraping_rules.c.data_source_id == data_sources.c.id,
            )
        )
        .where(
            sa.cast(scraping_rules.c.status, sa.String) == "ACTIVE",
            sa.cast(data_sources.c.status, sa.String) == "ACTIVE",
        )
        .order_by(scraping_rules.c.id.asc())
    ).mappings()

    now = datetime.now(timezone.utc)
    payload: list[dict[str, object]] = []
    for row in rows:
        rule_id = int(row["id"])
        data_source_id = int(row["data_source_id"])
        timezone_value = str(row["timezone"] or "Asia/Shanghai")
        granularity = str(row["granularity"] or "DAY")
        incremental_mode = str(row["incremental_mode"] or "BY_DATE")
        data_latency = str(row["data_latency"] or "T+1")

        payload.extend(
            [
                {
                    "created_at": now,
                    "updated_at": now,
                    "name": f"shop-dashboard-full-sync-{rule_id}",
                    "task_type": "SHOP_DASHBOARD_COLLECTION",
                    "data_source_id": data_source_id,
                    "rule_id": rule_id,
                    "schedule": {
                        "cron": "0 2 * * *",
                        "timezone": timezone_value,
                        "kwargs": {
                            "execution_id": f"cron_full_sync_{rule_id}",
                            "granularity": granularity,
                            "timezone": timezone_value,
                            "incremental_mode": incremental_mode,
                            "data_latency": data_latency,
                        },
                    },
                    "status": "ACTIVE",
                },
                {
                    "created_at": now,
                    "updated_at": now,
                    "name": f"shop-dashboard-incremental-sync-{rule_id}",
                    "task_type": "SHOP_DASHBOARD_COLLECTION",
                    "data_source_id": data_source_id,
                    "rule_id": rule_id,
                    "schedule": {
                        "cron": "0 6,10,14,18 * * *",
                        "timezone": timezone_value,
                        "kwargs": {
                            "execution_id": f"cron_incremental_sync_{rule_id}",
                            "granularity": granularity,
                            "timezone": timezone_value,
                            "incremental_mode": incremental_mode,
                            "data_latency": data_latency,
                        },
                    },
                    "status": "ACTIVE",
                },
                {
                    "created_at": now,
                    "updated_at": now,
                    "name": f"shop-dashboard-cookie-health-check-{rule_id}",
                    "task_type": "SHOP_DASHBOARD_COLLECTION",
                    "data_source_id": data_source_id,
                    "rule_id": rule_id,
                    "schedule": {
                        "cron": "*/30 * * * *",
                        "timezone": timezone_value,
                        "kwargs": {
                            "execution_id": f"cron_cookie_health_check_{rule_id}",
                            "granularity": granularity,
                            "timezone": timezone_value,
                            "incremental_mode": incremental_mode,
                            "data_latency": data_latency,
                        },
                    },
                    "status": "ACTIVE",
                },
            ]
        )

    if payload:
        bind.execute(sa.insert(collection_jobs), payload)
