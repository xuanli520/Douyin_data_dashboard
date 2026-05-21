from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260521_02"
down_revision: Union[str, Sequence[str], None] = "20260521_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("shop_dashboard_scores"):
        columns = {
            column["name"] for column in inspector.get_columns("shop_dashboard_scores")
        }
        with op.batch_alter_table("shop_dashboard_scores") as batch_op:
            for name in (
                "total_score",
                "product_score",
                "logistics_score",
                "service_score",
                "bad_behavior_score",
            ):
                if name in columns:
                    batch_op.alter_column(name, existing_type=sa.Float(), nullable=True)
            if "status" not in columns:
                batch_op.add_column(
                    sa.Column(
                        "status",
                        sa.String(length=20),
                        nullable=False,
                        server_default="success",
                    )
                )
            if "reason" not in columns:
                batch_op.add_column(sa.Column("reason", sa.String(length=100)))
            if "error_code" not in columns:
                batch_op.add_column(sa.Column("error_code", sa.String(length=100)))
        if "status" not in columns:
            op.create_index(
                op.f("ix_shop_dashboard_scores_status"),
                "shop_dashboard_scores",
                ["status"],
            )

    for table_name in (
        "shop_dashboard_cold_metrics",
        "shop_dashboard_reviews",
        "shop_dashboard_violations",
    ):
        if inspector.has_table(table_name):
            op.drop_table(table_name)


def downgrade() -> None:
    pass
