"""repair shop dashboard score uniqueness

Revision ID: 20260316_02
Revises: 20260316_01
Create Date: 2026-03-16 15:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260316_02"
down_revision: Union[str, Sequence[str], None] = "20260316_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _constraint_exists(
    conn: sa.Connection,
    *,
    table_name: str,
    constraint_name: str,
) -> bool:
    result = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint
            WHERE conname = :constraint_name
              AND conrelid = to_regclass(:table_name)
            LIMIT 1
            """
        ),
        {
            "constraint_name": constraint_name,
            "table_name": table_name,
        },
    )
    return result.scalar_one_or_none() is not None


def _ensure_unique_constraint(
    conn: sa.Connection,
    *,
    table_name: str,
    constraint_name: str,
    columns: list[str],
) -> None:
    if _constraint_exists(
        conn,
        table_name=table_name,
        constraint_name=constraint_name,
    ):
        return
    op.create_unique_constraint(constraint_name, table_name, columns)


def upgrade() -> None:
    conn = op.get_bind()

    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY shop_id, metric_date
                        ORDER BY updated_at DESC NULLS LAST, id DESC
                    ) AS rn
                FROM shop_dashboard_scores
            )
            DELETE FROM shop_dashboard_scores AS score
            USING ranked
            WHERE score.id = ranked.id
              AND ranked.rn > 1
            """
        )
    )

    _ensure_unique_constraint(
        conn,
        table_name="shop_dashboard_scores",
        constraint_name="uq_shop_dashboard_score_day",
        columns=["shop_id", "metric_date"],
    )
    _ensure_unique_constraint(
        conn,
        table_name="shop_dashboard_reviews",
        constraint_name="uq_shop_dashboard_review_day",
        columns=["shop_id", "metric_date", "review_id"],
    )
    _ensure_unique_constraint(
        conn,
        table_name="shop_dashboard_violations",
        constraint_name="uq_shop_dashboard_violation_day",
        columns=["shop_id", "metric_date", "violation_id"],
    )
    _ensure_unique_constraint(
        conn,
        table_name="shop_dashboard_cold_metrics",
        constraint_name="uq_shop_dashboard_cold_metric_day_reason",
        columns=["shop_id", "metric_date", "reason"],
    )

    required_constraints = [
        ("shop_dashboard_scores", "uq_shop_dashboard_score_day"),
        ("shop_dashboard_reviews", "uq_shop_dashboard_review_day"),
        ("shop_dashboard_violations", "uq_shop_dashboard_violation_day"),
        ("shop_dashboard_cold_metrics", "uq_shop_dashboard_cold_metric_day_reason"),
    ]
    for table_name, constraint_name in required_constraints:
        if not _constraint_exists(
            conn,
            table_name=table_name,
            constraint_name=constraint_name,
        ):
            raise RuntimeError(
                f"missing unique constraint after migration: {constraint_name}"
            )


def downgrade() -> None:
    pass
