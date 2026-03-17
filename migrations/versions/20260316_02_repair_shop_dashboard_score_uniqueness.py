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
    columns: list[str],
) -> bool:
    inspector = sa.inspect(conn)
    if not inspector.has_table(table_name):
        return False

    for item in inspector.get_unique_constraints(table_name):
        if item.get("name") == constraint_name:
            return True
        if item.get("column_names") == columns:
            return True

    for item in inspector.get_indexes(table_name):
        if not item.get("unique"):
            continue
        if item.get("name") == constraint_name:
            return True
        if item.get("column_names") == columns:
            return True

    return False


def _ensure_unique_constraint(
    conn: sa.Connection,
    *,
    table_name: str,
    constraint_name: str,
    columns: list[str],
) -> None:
    inspector = sa.inspect(conn)
    if not inspector.has_table(table_name):
        return

    if _constraint_exists(
        conn,
        table_name=table_name,
        constraint_name=constraint_name,
        columns=columns,
    ):
        return

    if conn.dialect.name == "sqlite":
        op.create_index(constraint_name, table_name, columns, unique=True)
        return

    op.create_unique_constraint(constraint_name, table_name, columns)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("shop_dashboard_scores"):
        op.execute(
            sa.text(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY shop_id, metric_date
                            ORDER BY
                                CASE WHEN updated_at IS NULL THEN 1 ELSE 0 END,
                                updated_at DESC,
                                id DESC
                        ) AS rn
                    FROM shop_dashboard_scores
                )
                DELETE FROM shop_dashboard_scores
                WHERE id IN (
                    SELECT id FROM ranked WHERE rn > 1
                )
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
        (
            "shop_dashboard_scores",
            "uq_shop_dashboard_score_day",
            ["shop_id", "metric_date"],
        ),
        (
            "shop_dashboard_reviews",
            "uq_shop_dashboard_review_day",
            ["shop_id", "metric_date", "review_id"],
        ),
        (
            "shop_dashboard_violations",
            "uq_shop_dashboard_violation_day",
            ["shop_id", "metric_date", "violation_id"],
        ),
        (
            "shop_dashboard_cold_metrics",
            "uq_shop_dashboard_cold_metric_day_reason",
            ["shop_id", "metric_date", "reason"],
        ),
    ]
    for table_name, constraint_name, columns in required_constraints:
        if not inspector.has_table(table_name):
            continue
        if not _constraint_exists(
            conn,
            table_name=table_name,
            constraint_name=constraint_name,
            columns=columns,
        ):
            raise RuntimeError(
                f"missing unique constraint after migration: {constraint_name}"
            )


def downgrade() -> None:
    pass
