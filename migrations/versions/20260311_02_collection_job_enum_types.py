"""use enum types for collection_jobs columns

Revision ID: 20260311_02
Revises: 20260311_01
Create Date: 2026-03-11 23:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_02"
down_revision: Union[str, Sequence[str], None] = "20260311_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if not inspector.has_table("collection_jobs"):
        return
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
                SELECT 1 FROM pg_type WHERE typname = 'collectionjobstatus'
            ) THEN
                CREATE TYPE collectionjobstatus AS ENUM (
                    'ACTIVE',
                    'INACTIVE'
                );
            END IF;
        END$$;
        """
    )
    op.execute(
        """
        ALTER TABLE collection_jobs
        ALTER COLUMN task_type TYPE tasktype
        USING task_type::tasktype
        """
    )
    op.execute(
        """
        ALTER TABLE collection_jobs
        ALTER COLUMN status TYPE collectionjobstatus
        USING status::collectionjobstatus
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if not inspector.has_table("collection_jobs"):
        return
    op.execute(
        """
        ALTER TABLE collection_jobs
        ALTER COLUMN status TYPE VARCHAR(32)
        USING status::text
        """
    )
    op.execute(
        """
        ALTER TABLE collection_jobs
        ALTER COLUMN task_type TYPE VARCHAR(64)
        USING task_type::text
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'collectionjobstatus'
            ) THEN
                DROP TYPE collectionjobstatus;
            END IF;
        END$$;
        """
    )
