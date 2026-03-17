"""fix task enum column types

Revision ID: 27e8976139e6
Revises: 60a123d3fa0a
Create Date: 2026-03-09 11:51:06.754187

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "27e8976139e6"
down_revision: Union[str, Sequence[str], None] = "60a123d3fa0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'tasktype'
            ) THEN
                CREATE TYPE tasktype AS ENUM (
                    'ETL_ORDERS',
                    'ETL_PRODUCTS',
                    'SHOP_DASHBOARD_COLLECTION'
                );
            END IF;
        END$$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'taskdefinitionstatus'
            ) THEN
                CREATE TYPE taskdefinitionstatus AS ENUM (
                    'ACTIVE',
                    'PAUSED',
                    'CANCELLED'
                );
            END IF;
        END$$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'taskexecutionstatus'
            ) THEN
                CREATE TYPE taskexecutionstatus AS ENUM (
                    'QUEUED',
                    'RUNNING',
                    'SUCCESS',
                    'FAILED',
                    'CANCELLED'
                );
            END IF;
        END$$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'tasktriggermode'
            ) THEN
                CREATE TYPE tasktriggermode AS ENUM (
                    'MANUAL',
                    'SCHEDULED',
                    'SYSTEM'
                );
            END IF;
        END$$;
        """
    )
    op.execute(
        """
        ALTER TABLE task_definitions
        ALTER COLUMN task_type TYPE tasktype
        USING task_type::tasktype
        """
    )
    op.execute(
        """
        ALTER TABLE task_definitions
        ALTER COLUMN status TYPE taskdefinitionstatus
        USING status::taskdefinitionstatus
        """
    )
    op.execute(
        """
        ALTER TABLE task_executions
        ALTER COLUMN status TYPE taskexecutionstatus
        USING status::taskexecutionstatus
        """
    )
    op.execute(
        """
        ALTER TABLE task_executions
        ALTER COLUMN trigger_mode TYPE tasktriggermode
        USING trigger_mode::tasktriggermode
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "task_executions",
        "trigger_mode",
        existing_type=sa.Enum(
            "MANUAL",
            "SCHEDULED",
            "SYSTEM",
            name="tasktriggermode",
        ),
        type_=sa.String(length=32),
        postgresql_using="trigger_mode::text",
    )
    op.alter_column(
        "task_executions",
        "status",
        existing_type=sa.Enum(
            "QUEUED",
            "RUNNING",
            "SUCCESS",
            "FAILED",
            "CANCELLED",
            name="taskexecutionstatus",
        ),
        type_=sa.String(length=32),
        postgresql_using="status::text",
    )
    op.alter_column(
        "task_definitions",
        "status",
        existing_type=sa.Enum(
            "ACTIVE",
            "PAUSED",
            "CANCELLED",
            name="taskdefinitionstatus",
        ),
        type_=sa.String(length=32),
        postgresql_using="status::text",
    )
    op.alter_column(
        "task_definitions",
        "task_type",
        existing_type=sa.Enum(
            "ETL_ORDERS",
            "ETL_PRODUCTS",
            "SHOP_DASHBOARD_COLLECTION",
            name="tasktype",
        ),
        type_=sa.String(length=64),
        postgresql_using="task_type::text",
    )
